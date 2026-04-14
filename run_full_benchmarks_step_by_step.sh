#!/usr/bin/env bash
set -euo pipefail

# 兼容入口：按系统“一个一个”执行（不会串联多个系统）
# 用法：
#   bash run_full_benchmarks_step_by_step.sh --system lightrag
#   bash run_full_benchmarks_step_by_step.sh --system hipporag
#   bash run_full_benchmarks_step_by_step.sh --system raptor

usage() {
  cat <<'EOF'
Usage:
  bash run_full_benchmarks_step_by_step.sh --system <lightrag|hipporag|raptor>

Notes:
  - 该脚本一次只运行一个系统，不会并行或串联其他系统。
  - 透传环境变量：CONDA_ENV, BENCH, R_MODES, LOG_DIR
EOF
}

SYSTEM=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --system)
      SYSTEM="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$SYSTEM" ]]; then
  echo "[ERROR] --system is required." >&2
  usage
  exit 2
fi

case "$SYSTEM" in
  lightrag)
    exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_lightrag_full_anaconda.sh"
    ;;
  hipporag)
    exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_hipporag_full_anaconda.sh"
    ;;
  raptor)
    exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_raptor_full_anaconda.sh"
    ;;
  *)
    echo "[ERROR] Invalid system: $SYSTEM" >&2
    usage
    exit 2
    ;;
esac
