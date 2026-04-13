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
from uuid import uuid4

import requests

logger = logging.getLogger(__name__)

from simpleMem_src import Evidence


class LightRAGBenchMemory:
    """LightRAG HTTP 封装。"""

    def __init__(self, save_dir: str):
        self.save_dir = save_dir
        self._buffer: List[str] = []

        self._base_url = os.getenv("LIGHTRAG_URL", "http://127.0.0.1:9621").rstrip("/")
        self._api_key = os.getenv("LIGHTRAG_API_KEY", "")
        self._mode = os.getenv("LIGHTRAG_MODE", "mix")
        self._timeout = 60

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

    def build_index(self) -> None:
        """异步提交文档并轮询状态直到完成。"""
        if not self._buffer:
            return

        texts = [self._with_namespace(t) for t in self._buffer]
        t0 = time.time()

        logger.info("[LightRAGBenchMemory] 提交建库文本，chunks=%d ns=%s", len(texts), self._ns)
        submit_payload = self._post_json("/documents/texts", {"texts": texts})
        track_id = self._extract_track_id(submit_payload)
        if not track_id:
            raise RuntimeError(f"[LightRAGBenchMemory] 建库返回缺少 track_id: {submit_payload}")

        deadline = time.time() + 300  # 最多等待 5 分钟
        last_status: Dict[str, Any] = {}
        while time.time() < deadline:
            status = self._get_json(f"/track_status/{track_id}")
            logger.debug("[LightRAGBenchMemory] track_status=%s", status)
            last_status = status
            if self._is_processed(status):
                self.ingest_chunks = len(self._buffer)
                self.ingest_time_ms = (time.time() - t0) * 1000
                logger.info("[LightRAGBenchMemory] 建库完成，耗时=%.1fms", self.ingest_time_ms)
                return
            if self._is_failed(status):
                raise RuntimeError(f"[LightRAGBenchMemory] 建库失败: {status}")
            time.sleep(1.0)

        raise RuntimeError(f"[LightRAGBenchMemory] 建库超时，最后状态: {last_status}")

    def retrieve(self, query: str, top_k: int = 10) -> List[Evidence]:
        payload = {
            "query": query,
            "mode": self._mode,
            "include_references": True,
            "include_chunk_content": True,
        }
        logger.debug("[LightRAGBenchMemory] 检索 query=%s top_k=%d mode=%s", query[:80], top_k, self._mode)
        data = self._post_json("/query", payload)

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
        self._ns = f"{Path(self.save_dir).name}_{uuid4().hex[:8]}"
        self.ingest_chunks = 0
        self.ingest_time_ms = 0.0

    def audit_ingest(self) -> Dict[str, Any]:
        return {
            "ingest_chunks": self.ingest_chunks,
            "ingest_time_ms": round(self.ingest_time_ms),
            "ingest_llm_calls": 0,
            "ingest_llm_prompt_tokens": 0,
            "ingest_llm_completion_tokens": 0,
        }
