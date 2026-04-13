# -*- coding: utf-8 -*-
"""MemGPT/Letta benchmark wrapper。

设计目标：
1. 与 bench_r123.py 统一接口兼容（add_memory / build_index / retrieve / reset / audit_ingest）。
2. 采用“先缓存、后 flush”模式：add_memory 只缓存，build_index 再写入 Letta archival memory。
3. 强隔离：reset 后不复用旧 agent，避免跨 case 污染。
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

from simpleMem_src import get_config, Evidence


class MemGPTBenchMemory:
    """MemGPT/Letta 评测封装。"""

    def __init__(self, save_dir: str):
        self.save_dir = save_dir
        self._buffer: List[str] = []

        self._base_url = os.getenv("LETTA_BASE_URL", "http://127.0.0.1:8283")
        self._api_key = os.getenv("LETTA_API_KEY") or None

        # 动态导入：优先 letta_client（官方 SDK 名称），兼容可能的 letta 包。
        letta_cls = None
        try:
            from letta_client import Letta as _Letta  # type: ignore
            letta_cls = _Letta
        except Exception:
            from letta import Letta as _Letta  # type: ignore
            letta_cls = _Letta

        self._client = letta_cls(base_url=self._base_url, api_key=self._api_key)
        self._agent_id: Optional[str] = None
        self._agent_name: Optional[str] = None

        self.ingest_chunks = 0
        self.ingest_time_ms = 0.0

    def add_memory(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """仅缓存文本，等待 build_index 统一写入。"""
        if text:
            self._buffer.append(text)
            logger.debug("[MemGPTBenchMemory] 缓存记忆片段，当前 buffer=%d", len(self._buffer))

    def _resolve_model_fields(self) -> Dict[str, Any]:
        """解析模型参数：环境变量优先，config.yaml 兜底。"""
        conf = get_config()
        model = os.getenv("LETTA_MODEL") or conf.llm.get("model")
        embedding = os.getenv("LETTA_EMBEDDING") or conf.embedding.get("model")
        return {
            "model": model,
            "embedding": embedding,
        }

    def _ensure_agent(self) -> None:
        """确保 agent 已创建。"""
        if self._agent_id:
            return

        model_fields = self._resolve_model_fields()
        base_name = Path(self.save_dir).name or "memgpt_bench"
        unique_suffix = uuid.uuid4().hex[:8]
        self._agent_name = f"{base_name}_{unique_suffix}"

        payload = {
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

        # 兼容不同 SDK 返回类型（对象 / dict）
        logger.info("[MemGPTBenchMemory] 创建 Letta agent: %s", self._agent_name)
        agent = self._client.agents.create(**payload)
        self._agent_id = getattr(agent, "id", None) or (agent.get("id") if isinstance(agent, dict) else None)
        if not self._agent_id:
            raise RuntimeError("[MemGPTBenchMemory] 创建 Letta agent 失败：未获得 agent_id")

    def build_index(self) -> None:
        """将缓存批量写入 Letta archival passages。"""
        if not self._buffer:
            return
        self._ensure_agent()

        logger.info("[MemGPTBenchMemory] 开始 flush buffer 到 Letta，chunks=%d", len(self._buffer))
        t0 = time.time()
        for chunk in self._buffer:
            self._client.agents.passages.create(agent_id=self._agent_id, text=chunk)
        self.ingest_time_ms = (time.time() - t0) * 1000
        self.ingest_chunks = len(self._buffer)
        logger.info("[MemGPTBenchMemory] flush 完成，耗时=%.1fms", self.ingest_time_ms)

    def retrieve(self, query: str, top_k: int = 10) -> List[Evidence]:
        self._ensure_agent()
        logger.debug("[MemGPTBenchMemory] 检索 query=%s top_k=%d", query[:80], top_k)
        resp = self._client.agents.passages.search(agent_id=self._agent_id, query=query, top_k=top_k)

        items = getattr(resp, "results", None)
        if items is None and isinstance(resp, dict):
            items = resp.get("results", [])
        if items is None:
            items = []

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
            # 尝试删除远端 agent；若 SDK/服务端不支持，则降级为仅丢弃本地引用。
            try:
                self._client.agents.delete(agent_id=self._agent_id)
            except Exception:
                try:
                    self._client.agents.delete(self._agent_id)
                except Exception:
                    pass

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
