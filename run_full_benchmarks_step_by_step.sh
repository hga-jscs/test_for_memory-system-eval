#!/usr/bin/env bash
set -euo pipefail

# 顺序执行（一个一个跑）:
#   1) lightrag
#   2) hipporag
#   3) raptor
#   4) memgpt
# 默认覆盖 3 benchmark × r1,r2,r3（等价 bench_r123 --bench all --r r1,r2,r3）。

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${LOG_DIR:-logs/full_step_by_step_${TS}}"
BENCH="${BENCH:-all}"
R_MODES="${R_MODES:-r1,r2,r3}"
mkdir -p "$LOG_DIR"

SYSTEMS=(lightrag hipporag raptor memgpt)

prefix_stream() {
  local tag="$1"
  awk -v t="$tag" '{
    cmd="date +%H:%M:%S"
    cmd | getline now
    close(cmd)
    printf("[%s][%s] %s\n", now, t, $0)
    fflush()
  }'
}

run_one_system() {
  local system="$1"
  local logfile="$LOG_DIR/${system}.log"

  echo ""
  echo "================================================================"
  echo "[START] system=${system}  bench=${BENCH}  r=${R_MODES}  at $(date)"
  echo "[INFO ] logfile=${logfile}"
  echo "================================================================"

  {
    echo "=== START system=${system} bench=${BENCH} r=${R_MODES} ==="
    PYTHONUNBUFFERED=1 python3 bench_r123.py --system "$system" --bench "$BENCH" --r "$R_MODES"
    echo "=== DONE system=${system} ==="
  } 2>&1 | tee "$logfile" | prefix_stream "$system"

  echo "[DONE ] system=${system}  at $(date)"
}

echo "=============================================================="
echo "顺序全量评测启动（一个一个跑）: $(date)"
echo "ROOT_DIR=$ROOT_DIR"
echo "LOG_DIR=$LOG_DIR"
echo "BENCH=$BENCH"
echo "R_MODES=$R_MODES"
echo "SYSTEMS=${SYSTEMS[*]}"
echo "=============================================================="

for system in "${SYSTEMS[@]}"; do
  run_one_system "$system"
done

echo "=============================================================="
echo "全部完成（顺序执行）: $(date)"
echo "日志目录: $LOG_DIR"
echo "=============================================================="
