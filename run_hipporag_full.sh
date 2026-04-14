#!/usr/bin/env bash
set -euo pipefail

# HippoRAG 全 benchmark 评测脚本（memory_probe + structmemeval + amemgym）
# 支持可视化调试输出：每行日志自动加时间戳和系统名前缀。

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${LOG_DIR:-logs/hipporag_full_${TS}}"
R_MODES="${R_MODES:-r1,r2,r3}"
START="${START:-0}"
END="${END:-}"
mkdir -p "$LOG_DIR"

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

run_bench() {
  local bench="$1"
  local logfile="$LOG_DIR/${bench}.log"
  echo "=============================================================="
  echo "[START] system=hipporag bench=${bench} r=${R_MODES} at $(date)"
  echo "[INFO ] logfile=${logfile}"

  local cmd=(python3 bench_r123.py --system hipporag --bench "$bench" --r "$R_MODES")
  if [[ "$bench" == "amemgym" && -n "$END" ]]; then
    cmd+=(--start "$START" --end "$END")
  fi

  PYTHONUNBUFFERED=1 "${cmd[@]}" 2>&1 | tee "$logfile" | prefix_stream "hipporag/${bench}"
  echo "[DONE ] system=hipporag bench=${bench} at $(date)"
}

for bench in memory_probe structmemeval amemgym; do
  run_bench "$bench"
done

echo "=============================================================="
echo "HippoRAG 全 benchmark 评测完成: $(date)"
echo "日志目录: $LOG_DIR"
echo "=============================================================="
