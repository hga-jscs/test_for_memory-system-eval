#!/usr/bin/env bash
set -euo pipefail

# 仅跑 LightRAG（独立脚本，不串联其他系统）
# 用法：bash run_lightrag_full_anaconda.sh

CONDA_ENV="${CONDA_ENV:-mem-eval}"
R_MODES="${R_MODES:-r1,r2,r3}"
BENCH="${BENCH:-all}"
LOG_DIR="${LOG_DIR:-logs/lightrag_full_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/lightrag.log"

if command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
elif [[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
  # 标准 Anaconda 安装路径
  source "$HOME/anaconda3/etc/profile.d/conda.sh"
else
  echo "[ERROR] 找不到 conda，请先安装 Anaconda/Miniconda。" >&2
  exit 1
fi

conda activate "$CONDA_ENV"

awk_prefix() {
  awk -v t="lightrag" '{
    cmd="date +%H:%M:%S"
    cmd | getline now
    close(cmd)
    printf("[%s][%s] %s\n", now, t, $0)
    fflush()
  }'
}

echo "[INFO] conda env: $CONDA_ENV"
echo "[INFO] BENCH=$BENCH R_MODES=$R_MODES"
echo "[INFO] LOG_FILE=$LOG_FILE"

PYTHONUNBUFFERED=1 python3 bench_r123.py --system lightrag --bench "$BENCH" --r "$R_MODES" 2>&1 | tee "$LOG_FILE" | awk_prefix
