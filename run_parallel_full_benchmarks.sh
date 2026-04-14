#!/usr/bin/env bash
set -euo pipefail

# 兼容入口：历史脚本名保留，但行为改为“单系统单次执行”
# 防止误触发并行运行。

echo "[INFO] run_parallel_full_benchmarks.sh 已切换为安全模式：一次只运行一个系统。"
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_full_benchmarks_step_by_step.sh" "$@"
