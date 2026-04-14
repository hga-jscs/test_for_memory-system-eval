# -*- coding: utf-8 -*-
"""本地可观测 fallback 检索实现。

用于外部依赖不可用（如 Conda 首次部署缺库、服务未启动）时，
确保 smoke test/benchmark 至少可以完成端到端链路并输出可调试信息。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-']+")


@dataclass
class LocalEvidence:
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class LocalDebugMemory:
    """一个稳定、零外部依赖的本地内存检索器（token overlap）。"""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self._buffer: List[str] = []
        self._built = False
        self.ingest_chunks = 0
        self.ingest_time_ms = 0.0

    def add_memory(self, text: str) -> None:
        if text:
            self._buffer.append(text)

    def build_index(self) -> None:
        t0 = time.time()
        self.ingest_chunks = len(self._buffer)
        self._built = True
        self.ingest_time_ms = (time.time() - t0) * 1000

    def retrieve(self, query: str, top_k: int = 5) -> List[LocalEvidence]:
        if not self._built:
            return []
        q_tokens = set(self._tokens(query))
        scored = []
        for idx, text in enumerate(self._buffer):
            t_tokens = set(self._tokens(text))
            overlap = len(q_tokens & t_tokens)
            union = len(q_tokens | t_tokens) or 1
            score = overlap / union
            scored.append((score, idx, text))

        scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
        out: List[LocalEvidence] = []
        for rank, (score, idx, text) in enumerate(scored[:top_k], start=1):
            out.append(
                LocalEvidence(
                    content=text,
                    metadata={
                        "source": f"{self.source_name}-local-fallback",
                        "rank": rank,
                        "score": round(float(score), 4),
                        "chunk_index": idx,
                    },
                )
            )
        return out

    def reset(self) -> None:
        self._buffer = []
        self._built = False
        self.ingest_chunks = 0
        self.ingest_time_ms = 0.0

    def audit_ingest(self) -> Dict[str, Any]:
        return {
            "ingest_chunks": self.ingest_chunks,
            "ingest_time_ms": round(self.ingest_time_ms),
            "ingest_llm_calls": 0,
            "ingest_llm_prompt_tokens": 0,
            "ingest_llm_completion_tokens": 0,
            "backend": f"{self.source_name}-local-fallback",
        }

    @staticmethod
    def _tokens(text: str) -> List[str]:
        return [tok.lower() for tok in _TOKEN_RE.findall(text or "")]
