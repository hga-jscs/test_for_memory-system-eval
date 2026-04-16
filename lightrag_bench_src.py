# -*- coding: utf-8 -*-
"""LightRAG benchmark wrapper（HTTP Server 方案）。

实现原则：
1. add_memory 先缓存，build_index 再统一提交。
2. 每个实例生成独立 namespace，检索只返回当前 namespace 的 chunk，避免脏数据污染。
3. 所有 HTTP 调用都包含 timeout、状态码检查与错误消息。
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging
import json
from uuid import uuid4

import requests

logger = logging.getLogger(__name__)

from simpleMem_src import Evidence
from local_debug_memory import LocalDebugMemory


class LightRAGBenchMemory:
    """LightRAG HTTP 封装。"""

    def __init__(self, save_dir: str):
        self.save_dir = save_dir
        self._buffer: List[str] = []

        self._base_url = os.getenv("LIGHTRAG_URL", "http://127.0.0.1:9621").rstrip("/")
        self._api_key = os.getenv("LIGHTRAG_API_KEY", "")
        self._mode = os.getenv("LIGHTRAG_MODE", "mix")
        self._timeout = 60
        self._fallback = LocalDebugMemory("LightRAG")
        self._use_fallback = os.getenv("LIGHTRAG_FORCE_LOCAL", "0") == "1"

        self._ns = f"{Path(save_dir).name}_{uuid4().hex[:8]}"
        self.ingest_chunks = 0
        self.ingest_time_ms = 0.0

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _with_namespace(self, text: str) -> str:
        return f"[NS: {self._ns}]\n{text}"

    def add_memory(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        if text:
            self._buffer.append(text)
            self._fallback.add_memory(text)
            logger.debug("[LightRAGBenchMemory] 缓存记忆片段，当前 buffer=%d", len(self._buffer))

    def _post_json(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            resp = requests.post(url, json=body, headers=self._headers(), timeout=self._timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"[LightRAGBenchMemory] POST {path} 失败: {e}") from e

        try:
            return resp.json()
        except Exception as e:
            raise RuntimeError(f"[LightRAGBenchMemory] POST {path} 返回非 JSON") from e

    def _get_json(self, path: str) -> Dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=self._timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"[LightRAGBenchMemory] GET {path} 失败: {e}") from e

        try:
            return resp.json()
        except Exception as e:
            raise RuntimeError(f"[LightRAGBenchMemory] GET {path} 返回非 JSON") from e

    def _try_get_json(self, path: str) -> Optional[Dict[str, Any]]:
        """容错版 GET：失败返回 None，避免中断主流程。"""
        try:
            return self._get_json(path)
        except Exception as e:
            logger.warning("[LightRAGBenchMemory] GET %s 失败（容错继续）: %s", path, e)
            return None

    def _extract_track_id(self, payload: Dict[str, Any]) -> Optional[str]:
        candidates = [
            payload.get("track_id"),
            payload.get("id"),
            (payload.get("data") or {}).get("track_id") if isinstance(payload.get("data"), dict) else None,
        ]
        for x in candidates:
            if isinstance(x, str) and x:
                return x
        return None

    def _is_processed(self, payload: Dict[str, Any]) -> bool:
        txt = str(payload).lower()
        return any(k in txt for k in ["processed", "completed", "success", "done"])

    def _is_failed(self, payload: Dict[str, Any]) -> bool:
        txt = str(payload).lower()
        return any(k in txt for k in ["failed", "error"])

    def _status_preview(self, status: Dict[str, Any]) -> str:
        try:
            compact = json.dumps(status, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            compact = str(status)
        if len(compact) > 220:
            compact = compact[:220] + "...(truncated)"
        return compact

    def build_index(self) -> None:
        """异步提交文档并轮询状态直到完成。"""
        if not self._buffer:
            return
        if self._use_fallback:
            logger.warning("[LightRAGBenchMemory] 使用本地 fallback（LIGHTRAG_FORCE_LOCAL=1）")
            self._fallback.build_index()
            self.ingest_chunks = self._fallback.ingest_chunks
            self.ingest_time_ms = self._fallback.ingest_time_ms
            return

        texts = [self._with_namespace(t) for t in self._buffer]
        t0 = time.time()

        logger.info("[LightRAGBenchMemory] 提交建库文本，chunks=%d ns=%s", len(texts), self._ns)
        try:
            submit_payload = self._post_json("/documents/texts", {"texts": texts})
        except Exception as e:
            logger.warning("[LightRAGBenchMemory] 服务不可用，自动降级本地 fallback: %s", e)
            self._use_fallback = True
            self._fallback.build_index()
            self.ingest_chunks = self._fallback.ingest_chunks
            self.ingest_time_ms = self._fallback.ingest_time_ms
            return
        track_id = self._extract_track_id(submit_payload)
        if not track_id:
            logger.warning(
                "[LightRAGBenchMemory] 建库返回缺少 track_id，自动降级到本地 fallback。payload=%s",
                self._status_preview(submit_payload),
            )
            self._use_fallback = True
            self._fallback.build_index()
            self.ingest_chunks = self._fallback.ingest_chunks
            self.ingest_time_ms = (time.time() - t0) * 1000
            logger.info("[LightRAGBenchMemory] fallback 建库完成，耗时=%.1fms", self.ingest_time_ms)
            return

        deadline = time.time() + 300  # 最多等待 5 分钟
        total_wait_s = 300
        last_status: Dict[str, Any] = {}
        poll_round = 0
        while time.time() < deadline:
            poll_round += 1
            elapsed = int(total_wait_s - max(0, deadline - time.time()))
            logger.info(
                "[LightRAGBenchMemory] build_index 轮询中 track_id=%s round=%d elapsed=%ds/%ds",
                track_id,
                poll_round,
                elapsed,
                total_wait_s,
            )
            status = self._try_get_json(f"/track_status/{track_id}")
            if status is None:
                logger.warning(
                    "[LightRAGBenchMemory] 无法获取 track_status（可能任务被清理或接口不兼容），降级到本地 fallback。track_id=%s",
                    track_id,
                )
                self._use_fallback = True
                self._fallback.build_index()
                self.ingest_chunks = self._fallback.ingest_chunks
                self.ingest_time_ms = (time.time() - t0) * 1000
                logger.info("[LightRAGBenchMemory] fallback 建库完成，耗时=%.1fms", self.ingest_time_ms)
                return
            logger.debug("[LightRAGBenchMemory] track_status=%s", self._status_preview(status))
            last_status = status
            if self._is_processed(status):
                self.ingest_chunks = len(self._buffer)
                self.ingest_time_ms = (time.time() - t0) * 1000
                logger.info("[LightRAGBenchMemory] 建库完成，耗时=%.1fms", self.ingest_time_ms)
                return
            if self._is_failed(status):
                logger.error("[LightRAGBenchMemory] 远端建库失败，状态: %s", self._status_preview(status))
                logger.warning("[LightRAGBenchMemory] 自动切换到本地 fallback，保证评测流程可继续")
                self._use_fallback = True
                self._fallback.build_index()
                self.ingest_chunks = self._fallback.ingest_chunks
                self.ingest_time_ms = (time.time() - t0) * 1000
                logger.info("[LightRAGBenchMemory] fallback 建库完成，耗时=%.1fms", self.ingest_time_ms)
                return
            time.sleep(1.0)

        logger.error("[LightRAGBenchMemory] 建库超时，最后状态: %s", self._status_preview(last_status))
        logger.warning("[LightRAGBenchMemory] 自动切换到本地 fallback，保证评测流程可继续")
        self._use_fallback = True
        self._fallback.build_index()
        self.ingest_chunks = self._fallback.ingest_chunks
        self.ingest_time_ms = (time.time() - t0) * 1000
        logger.info("[LightRAGBenchMemory] fallback 建库完成，耗时=%.1fms", self.ingest_time_ms)

    def retrieve(self, query: str, top_k: int = 10) -> List[Evidence]:
        if self._use_fallback:
            return [Evidence(content=x.content, metadata=x.metadata) for x in self._fallback.retrieve(query, top_k=top_k)]
        payload = {
            "query": query,
            "mode": self._mode,
            "include_references": True,
            "include_chunk_content": True,
        }
        logger.debug("[LightRAGBenchMemory] 检索 query=%s top_k=%d mode=%s", query[:80], top_k, self._mode)
        try:
            data = self._post_json("/query", payload)
        except Exception as e:
            logger.warning("[LightRAGBenchMemory] 检索降级本地 fallback: %s", e)
            self._use_fallback = True
            return [Evidence(content=x.content, metadata=x.metadata) for x in self._fallback.retrieve(query, top_k=top_k)]

        references = data.get("references", []) if isinstance(data, dict) else []
        prefix = f"[NS: {self._ns}]"

        evidences: List[Evidence] = []
        rank = 0
        for ref in references:
            content = (ref or {}).get("content", "") if isinstance(ref, dict) else ""
            if not isinstance(content, str):
                continue
            if not content.startswith(prefix):
                continue

            cleaned = content[len(prefix):].lstrip("\n ")
            rank += 1
            meta = {
                "source": "LightRAG",
                "rank": rank,
                "score": 0.0,
                "file_path": ref.get("file_path") if isinstance(ref, dict) else None,
                "reference_id": ref.get("reference_id") if isinstance(ref, dict) else None,
            }
            evidences.append(Evidence(content=cleaned, metadata=meta))
            if len(evidences) >= top_k:
                break

        logger.debug("[LightRAGBenchMemory] 返回证据条数=%d ns=%s", len(evidences), self._ns)
        return evidences

    def reset(self) -> None:
        """不依赖服务端删除，直接切换 namespace，保证后续检索隔离。"""
        self._buffer = []
        self._fallback.reset()
        self._ns = f"{Path(self.save_dir).name}_{uuid4().hex[:8]}"
        self.ingest_chunks = 0
        self.ingest_time_ms = 0.0

    def audit_ingest(self) -> Dict[str, Any]:
        backend = "LightRAG-http" if not self._use_fallback else "LightRAG-local-fallback"
        return {
            "ingest_chunks": self.ingest_chunks,
            "ingest_time_ms": round(self.ingest_time_ms),
            "ingest_llm_calls": 0,
            "ingest_llm_prompt_tokens": 0,
            "ingest_llm_completion_tokens": 0,
            "backend": backend,
        }
