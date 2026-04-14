#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RAPTOR bench wrapper（支持本地 fallback，便于 Conda 环境快速验证）。"""
from __future__ import annotations

import sys
import threading
import time as _time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from local_debug_memory import LocalDebugMemory

import logging

logger = logging.getLogger(__name__)

# RAPTOR repo path
_RAPTOR_REPO = str(Path(__file__).resolve().parent.parent / "memoRaxis" / "external" / "raptor_repo")
if _RAPTOR_REPO not in sys.path:
    sys.path.insert(0, _RAPTOR_REPO)


@dataclass
class Evidence:
    content: str
    metadata: dict


def _cosine_distance(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 1.0
    cosine = dot / (na * nb)
    return 1.0 - max(-1.0, min(1.0, cosine))


class _NoQAModel:
    def answer_question(self, *args, **kwargs):
        return ""


class _CompatEmbeddingModel:
    def __init__(self):
        from simpleMem_src import get_config

        conf = get_config().embedding
        self.base_url = conf.get("base_url")
        self.api_key = conf.get("api_key")
        self.model = conf.get("model", "text-embedding-v3")
        from openai import OpenAI

        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def create_embedding(self, text: str):
        text = text.replace("\n", " ")
        return self._client.embeddings.create(input=text, model=self.model).data[0].embedding


class _CompatSummarizationModel:
    def __init__(self):
        from simpleMem_src import get_config

        conf = get_config().llm
        from openai import OpenAI

        self._client = OpenAI(api_key=conf.get("api_key"), base_url=conf.get("base_url"))
        self.model = conf.get("model")
        self.llm_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._stats_lock = threading.Lock()

    def summarize(self, context, max_tokens=180):
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a careful summarizer."},
                {"role": "user", "content": f"Summarize briefly:\n{context}"},
            ],
            temperature=0.2,
            max_tokens=max(32, int(max_tokens or 180)),
        )
        with self._stats_lock:
            self.llm_calls += 1
            self.prompt_tokens += getattr(resp.usage, "prompt_tokens", 0) or 0
            self.completion_tokens += getattr(resp.usage, "completion_tokens", 0) or 0
        return (resp.choices[0].message.content or "").strip() or (context or "")[:2000]


class RaptorBenchMemory:
    def __init__(
        self,
        save_dir: str = "/tmp/raptor_bench",
        tb_num_layers: int = 3,
        tb_max_tokens: int = 200,
        tb_summarization_length: int = 120,
        tr_threshold: float = 0.5,
        tr_top_k: int = 10,
        chunk_size: int = 1000,
    ):
        self.save_dir = save_dir
        self._chunk_size = chunk_size
        self._buffer: List[str] = []

        self._tb_num_layers = tb_num_layers
        self._tb_max_tokens = tb_max_tokens
        self._tb_summarization_length = tb_summarization_length
        self._tr_threshold = tr_threshold
        self._tr_top_k = tr_top_k

        self._emb = None
        self._summ = None
        self._ra: Optional[object] = None
        self._ingest_time_ms = 0
        self._fallback = LocalDebugMemory("RAPTOR")
        self._use_fallback = False

    def add_memory(self, text: str) -> None:
        for chunk in self._text_to_chunks(text):
            self._buffer.append(chunk)
            self._fallback.add_memory(chunk)

    def add_text(self, text: str) -> None:
        self.add_memory(text)

    def _text_to_chunks(self, text: str) -> List[str]:
        if len(text) <= self._chunk_size:
            return [text]
        chunks = []
        while text:
            if len(text) <= self._chunk_size:
                chunks.append(text)
                break
            cut = text.rfind("\n", 0, self._chunk_size)
            if cut <= 0:
                cut = text.rfind(" ", 0, self._chunk_size)
            if cut <= 0:
                cut = self._chunk_size
            chunks.append(text[:cut].rstrip())
            text = text[cut:].lstrip()
        return chunks

    def _make_config(self):
        from raptor import RetrievalAugmentationConfig

        return RetrievalAugmentationConfig(
            embedding_model=self._emb,
            summarization_model=self._summ,
            qa_model=_NoQAModel(),
            tb_num_layers=self._tb_num_layers,
            tb_max_tokens=self._tb_max_tokens,
            tb_summarization_length=self._tb_summarization_length,
            tr_threshold=self._tr_threshold,
            tr_top_k=self._tr_top_k,
        )

    def build_index(self) -> None:
        if not self._buffer:
            return
        try:
            from raptor import RetrievalAugmentation

            self._emb = _CompatEmbeddingModel()
            self._summ = _CompatSummarizationModel()
            config = self._make_config()
            ra = RetrievalAugmentation(config=config, tree=None)
            text = "\n\n".join(self._buffer)
            t0 = _time.time()
            ra.add_documents(text)
            self._ingest_time_ms = int((_time.time() - t0) * 1000)
            self._ra = ra
            self._use_fallback = False
        except Exception as e:
            logger.warning("RAPTOR不可用，降级本地 fallback: %s", e)
            self._use_fallback = True
            self._fallback.build_index()
            self._ingest_time_ms = int(self._fallback.ingest_time_ms)

    def retrieve(self, query: str, top_k: int = 10) -> List[Evidence]:
        if self._use_fallback:
            return [Evidence(content=x.content, metadata=x.metadata) for x in self._fallback.retrieve(query, top_k)]
        if self._ra is None or getattr(self._ra, "tree", None) is None:
            return []

        context, layer_info = self._ra.retrieve(
            question=query,
            top_k=top_k,
            collapse_tree=True,
            return_layer_information=True,
        )
        q_emb = self._ra.retriever.create_embedding(query)
        emb_key = getattr(self._ra.retriever, "context_embedding_model", None) or "EMB"

        evidences: List[Evidence] = []
        for item in layer_info:
            idx = int(item["node_index"])
            layer = int(item["layer_number"])
            node = self._ra.tree.all_nodes[idx]
            node_emb = node.embeddings.get(emb_key) if isinstance(node.embeddings, dict) else node.embeddings
            score = 0.0
            if node_emb is not None:
                score = float(1.0 - _cosine_distance(q_emb, node_emb) / 2.0)
            evidences.append(Evidence(content=node.text, metadata={"source": "RAPTOR", "node_index": idx, "layer": layer, "score": score}))

        if not evidences and isinstance(context, str) and context.strip():
            evidences.append(Evidence(content=context, metadata={"source": "RAPTOR", "node_index": -1, "layer": -1, "score": 0.0}))
        return evidences

    def reset(self) -> None:
        self._ra = None
        self._buffer.clear()
        self._fallback.reset()
        self._ingest_time_ms = 0
        self._use_fallback = False

    def audit_ingest(self) -> dict:
        if self._use_fallback:
            return self._fallback.audit_ingest()
        llm_calls = getattr(self._summ, "llm_calls", 0) if self._summ is not None else 0
        prompt_tokens = getattr(self._summ, "prompt_tokens", 0) if self._summ is not None else 0
        completion_tokens = getattr(self._summ, "completion_tokens", 0) if self._summ is not None else 0
        n_nodes = len(self._ra.tree.all_nodes) if self._ra and getattr(self._ra, "tree", None) else 0
        n_layers = self._ra.tree.num_layers if self._ra and getattr(self._ra, "tree", None) else 0
        return {
            "ingest_chunks": len(self._buffer),
            "ingest_time_ms": self._ingest_time_ms,
            "ingest_llm_calls": llm_calls,
            "ingest_llm_prompt_tokens": prompt_tokens,
            "ingest_llm_completion_tokens": completion_tokens,
            "tree_nodes": n_nodes,
            "tree_layers": n_layers,
            "backend": "RAPTOR-tree",
        }
