#!/usr/bin/env bash
set -euo pipefail

echo "[INFO] 已切换为顺序执行模式（按你的要求一个一个跑）。"
echo "[INFO] 推荐直接使用: bash run_full_benchmarks_step_by_step.sh"

exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_full_benchmarks_step_by_step.sh"
