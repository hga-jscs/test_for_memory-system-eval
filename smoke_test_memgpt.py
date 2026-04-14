#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MemGPT/Letta smoke test（服务端 API 版）"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

SEP = "=" * 78


def _print_header(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")


def run_smoke(save_dir: str, top_k: int) -> int:
    from memgpt_bench_src import MemGPTBenchMemory

    _print_header("MemGPT/Letta Smoke Test")
    print(f"LETTA_BASE_URL={os.getenv('LETTA_BASE_URL', 'http://127.0.0.1:8283')}")

    mem = MemGPTBenchMemory(save_dir=save_dir)
    samples = [
        "For release v2.3, the final approver is Grace.",
        "Grace asked Henry to prepare rollback notes.",
        "The release review meeting is every Wednesday morning.",
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
    q = "Who is the final approver for release v2.3?"
    evidences = mem.retrieve(q, top_k=top_k)
    print(f"  Q: {q}")
    print(f"  Retrieved: {len(evidences)}")
    for i, ev in enumerate(evidences, start=1):
        print(f"    [{i}] rank={ev.metadata.get('rank')} | {ev.content[:120]}")

    ok = len(evidences) > 0 and any("Grace" in ev.content for ev in evidences)
    print(f"\n  RESULT: {'PASS' if ok else 'FAIL'}")

    print("\n[4/4] reset")
    mem.reset()
    print("  reset 完成")

    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="MemGPT/Letta smoke test")
    parser.add_argument("--save-dir", default="/tmp/smoke_memgpt_min", help="本地临时目录")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    try:
        return run_smoke(save_dir=args.save_dir, top_k=args.top_k)
    except Exception as exc:
        _print_header("MemGPT/Letta Smoke Test ERROR")
        print(f"错误: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
