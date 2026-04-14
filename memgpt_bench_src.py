# -*- coding: utf-8 -*-
"""MemGPT/Letta benchmark wrapper。

设计目标：
1. 与 bench_r123.py 统一接口兼容（add_memory / build_index / retrieve / reset / audit_ingest）。
2. 采用“先缓存、后 flush”模式：add_memory 只缓存，build_index 再写入 Letta archival memory。
3. 强隔离：reset 后不复用旧 agent，避免跨 case 污染。
4. SDK 不稳定时自动降级到 HTTP API，提升可运行性。
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Evidence:
    """最小兼容 Evidence 结构（避免强依赖 simpleMem_src/pydantic）。"""

    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemGPTBenchMemory:
    """MemGPT/Letta 评测封装。"""

    def __init__(self, save_dir: str):
        self.save_dir = save_dir
        self._buffer: List[str] = []

        self._base_url = os.getenv("LETTA_BASE_URL", "http://127.0.0.1:8283").rstrip("/")
        self._api_key = os.getenv("LETTA_API_KEY") or None

        self._client = None
        self._sdk_name = None
        try:
            from letta_client import Letta as _Letta  # type: ignore

            self._client = _Letta(base_url=self._base_url, api_key=self._api_key)
            self._sdk_name = "letta_client"
        except Exception:
            try:
                from letta import Letta as _Letta  # type: ignore

                self._client = _Letta(base_url=self._base_url, api_key=self._api_key)
                self._sdk_name = "letta"
            except Exception:
                self._client = None
                self._sdk_name = "http-only"

        self._agent_id: Optional[str] = None
        self._agent_name: Optional[str] = None

        self.ingest_chunks = 0
        self.ingest_time_ms = 0.0

        logger.info(
            "[MemGPTBenchMemory] 初始化完成: base_url=%s, mode=%s",
            self._base_url,
            self._sdk_name,
        )

    def add_memory(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """仅缓存文本，等待 build_index 统一写入。"""
        if text:
            self._buffer.append(text)
            logger.debug("[MemGPTBenchMemory] 缓存记忆片段，当前 buffer=%d", len(self._buffer))

    def _resolve_model_fields(self) -> Dict[str, Any]:
        """解析模型参数：环境变量优先，缺失则交给服务端默认。"""
        model = os.getenv("LETTA_MODEL") or None
        embedding = os.getenv("LETTA_EMBEDDING") or None
        return {"model": model, "embedding": embedding}

    def _http_request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self._base_url}{path}"
        data = None
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {e.code} {method} {path}: {body[:300]}") from e

    def _extract_id(self, obj: Any) -> Optional[str]:
        return getattr(obj, "id", None) or (obj.get("id") if isinstance(obj, dict) else None)

    def _create_agent(self, payload: Dict[str, Any]) -> str:
        if self._client is not None:
            try:
                agent = self._client.agents.create(**payload)
                aid = self._extract_id(agent)
                if aid:
                    return aid
            except Exception as e:
                logger.warning("[MemGPTBenchMemory] SDK 创建 agent 失败，降级 HTTP: %s", e)

        resp = self._http_request("POST", "/v1/agents", payload)
        aid = self._extract_id(resp)
        if not aid:
            raise RuntimeError("[MemGPTBenchMemory] 创建 Letta agent 失败：未获得 agent_id")
        return aid

    def _create_passage(self, agent_id: str, text: str) -> None:
        if self._client is not None:
            try:
                self._client.agents.passages.create(agent_id=agent_id, text=text)
                return
            except Exception as e:
                logger.warning("[MemGPTBenchMemory] SDK passages.create 失败，降级 HTTP: %s", e)

        self._http_request("POST", f"/v1/agents/{agent_id}/passages", {"text": text})

    def _search_passages(self, agent_id: str, query: str, top_k: int) -> List[Any]:
        if self._client is not None:
            try:
                resp = self._client.agents.passages.search(agent_id=agent_id, query=query, top_k=top_k)
                items = getattr(resp, "results", None)
                if items is None and isinstance(resp, dict):
                    items = resp.get("results", [])
                return items or []
            except Exception as e:
                logger.warning("[MemGPTBenchMemory] SDK passages.search 失败，降级 HTTP: %s", e)

        resp = self._http_request("POST", f"/v1/agents/{agent_id}/passages/search", {"query": query, "top_k": top_k})
        return resp.get("results", []) if isinstance(resp, dict) else []

    def _delete_agent(self, agent_id: str) -> None:
        if self._client is not None:
            for fn in (
                lambda: self._client.agents.delete(agent_id=agent_id),
                lambda: self._client.agents.delete(agent_id),
            ):
                try:
                    fn()
                    return
                except Exception:
                    pass
        try:
            self._http_request("DELETE", f"/v1/agents/{agent_id}")
        except Exception:
            pass

    def _ensure_agent(self) -> None:
        """确保 agent 已创建。"""
        if self._agent_id:
            return

        model_fields = self._resolve_model_fields()
        base_name = Path(self.save_dir).name or "memgpt_bench"
        unique_suffix = uuid.uuid4().hex[:8]
        self._agent_name = f"{base_name}_{unique_suffix}"

        payload: Dict[str, Any] = {
            "name": self._agent_name,
            "memory_blocks": [
                {"label": "persona", "value": ""},
                {"label": "human", "value": ""},
            ],
        }
        if model_fields.get("model"):
            payload["model"] = model_fields["model"]
        if model_fields.get("embedding"):
            payload["embedding"] = model_fields["embedding"]

        logger.info("[MemGPTBenchMemory] 创建 Letta agent: %s", self._agent_name)
        self._agent_id = self._create_agent(payload)

    def build_index(self) -> None:
        """将缓存批量写入 Letta archival passages。"""
        if not self._buffer:
            return
        self._ensure_agent()

        logger.info("[MemGPTBenchMemory] 开始 flush buffer 到 Letta，chunks=%d", len(self._buffer))
        t0 = time.time()
        for i, chunk in enumerate(self._buffer, start=1):
            self._create_passage(self._agent_id, chunk)
            if i % 50 == 0:
                logger.info("[MemGPTBenchMemory] flush 进度: %d/%d", i, len(self._buffer))

        self.ingest_time_ms = (time.time() - t0) * 1000
        self.ingest_chunks = len(self._buffer)
        logger.info("[MemGPTBenchMemory] flush 完成，耗时=%.1fms", self.ingest_time_ms)

    def retrieve(self, query: str, top_k: int = 10) -> List[Evidence]:
        self._ensure_agent()
        logger.debug("[MemGPTBenchMemory] 检索 query=%s top_k=%d", query[:80], top_k)
        items = self._search_passages(self._agent_id, query=query, top_k=top_k)

        evidences: List[Evidence] = []
        for i, item in enumerate(items[:top_k]):
            content = getattr(item, "text", None)
            if content is None and isinstance(item, dict):
                content = item.get("text") or item.get("content") or ""
            content = content or ""

            meta = {
                "source": "MemGPT/Letta",
                "rank": i + 1,
                "score": 0.0,
                "timestamp": getattr(item, "timestamp", None) if not isinstance(item, dict) else item.get("timestamp"),
                "passage_id": getattr(item, "id", None) if not isinstance(item, dict) else item.get("id"),
            }
            evidences.append(Evidence(content=content, metadata=meta))

        logger.debug("[MemGPTBenchMemory] 返回证据条数=%d", len(evidences))
        return evidences

    def reset(self) -> None:
        """重置缓存与 agent，确保下个 case 隔离。"""
        self._buffer = []

        if self._agent_id:
            self._delete_agent(self._agent_id)

        self._agent_id = None
        self._agent_name = None
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
