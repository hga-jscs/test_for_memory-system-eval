#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HippoRAG smoke test（最小可观测版）

目标：
1) 验证 add_memory/build_index/retrieve/reset 全链路可用
2) 打印可视化调试输出（audit + 命中证据）
3) 避免依赖外部 benchmark 数据文件
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


SEP = "=" * 78


def _print_header(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")


def run_smoke(save_dir: str, top_k: int) -> int:
    from hipporag_bench_src import HippoRAGMemory

    _print_header("HippoRAG Smoke Test")
    mem = HippoRAGMemory(save_dir=save_dir)

    samples = [
        "Alice moved to Seattle in March 2025 and now works at BlueRiver Labs.",
        "Alice's manager is Bob. Bob focuses on infra reliability and oncall planning.",
        "BlueRiver Labs plans a Kubernetes migration for Q2 2026.",
    ]

    print("[1/4] Ingest 样本记忆")
    for i, text in enumerate(samples, start=1):
        mem.add_memory(text)
        print(f"  - chunk#{i}: {text}")

    print("\n[2/4] build_index")
    mem.build_index()
    audit = mem.audit_ingest()
    print("  audit:")
    print(json.dumps(audit, indent=2, ensure_ascii=False))

    print("\n[3/4] retrieve")
    q = "Who is Alice's manager?"
    evidences = mem.retrieve(q, top_k=top_k)
    print(f"  Q: {q}")
    print(f"  Retrieved: {len(evidences)}")
    for i, ev in enumerate(evidences, start=1):
        print(f"    [{i}] score={ev.metadata.get('score', 0):.4f} | {ev.content[:120]}")

    ok = len(evidences) > 0 and any("Bob" in ev.content for ev in evidences)
    print(f"\n  RESULT: {'PASS' if ok else 'FAIL'}")

    print("\n[4/4] reset")
    mem.reset()
    print("  reset 完成")

    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="HippoRAG smoke test")
    parser.add_argument("--save-dir", default="/tmp/smoke_hipporag_min", help="索引目录")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    try:
        return run_smoke(save_dir=args.save_dir, top_k=args.top_k)
    except Exception as exc:
        _print_header("HippoRAG Smoke Test ERROR")
        print(f"错误: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
