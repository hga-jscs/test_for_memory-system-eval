#!/usr/bin/env bash
set -euo pipefail

# 用法：
#   bash run_smoke_four_anaconda.sh
# 可选：
#   FORCE_LOCAL=1 bash run_smoke_four_anaconda.sh
# 说明：
# - FORCE_LOCAL=1 时，四套系统都走本地 fallback，便于在无外部服务时验证流程。

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${ROOT_DIR}/logs/smoke_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${LOG_DIR}"

if [[ "${FORCE_LOCAL:-0}" == "1" ]]; then
  export LIGHTRAG_FORCE_LOCAL=1
  export LETTA_FORCE_LOCAL=1
  export HIPPORAG_FORCE_LOCAL=1
fi

echo "[INFO] Python: $(python --version 2>&1)"
echo "[INFO] Logs: ${LOG_DIR}"
echo "[INFO] FORCE_LOCAL=${FORCE_LOCAL:-0}"

run_one() {
  local name="$1"
  local cmd="$2"
  local log_file="${LOG_DIR}/${name}.log"

  echo "\n============================================================"
  echo "[RUN] ${name}"
  echo "[CMD] ${cmd}"
  echo "============================================================"

  set +e
  bash -lc "cd '${ROOT_DIR}' && ${cmd}" 2>&1 | tee "${log_file}"
  local rc=${PIPESTATUS[0]}
  set -e

  if [[ ${rc} -eq 0 ]]; then
    echo "[PASS] ${name} (log: ${log_file})"
  else
    echo "[FAIL] ${name} (rc=${rc}, log: ${log_file})"
    return ${rc}
  fi
}

run_one "lightrag" "python smoke_test_lightrag.py"
run_one "hipporag" "python smoke_test_hipporag.py"
run_one "raptor" "python smoke_test_raptor.py"
run_one "memgpt" "python smoke_test_memgpt.py"

echo "\n[DONE] 四个 smoke test 全部通过。"
echo "[DONE] 调试日志目录: ${LOG_DIR}"
