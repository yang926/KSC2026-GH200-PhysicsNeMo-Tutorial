#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
root="$(cd -- "$script_dir/.." && pwd -P)"
pycache="$(mktemp -d)"
trap 'rm -rf -- "$pycache"' EXIT

bash -n "$root/ksc2026" "$root/start-jupyter" "$root/jupyter-job.sh"
python3 -X "pycache_prefix=$pycache" -m py_compile \
    "$root/session-controller.py"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
    "$script_dir/test_session_controller.py" \
    "$script_dir/test_runtime_contract.py" \
    "$script_dir/test_entrypoint.py" -v

if rg -n '(^|[[:space:]])(apt|apt-get|pip|git|wget|curl)([[:space:]]|$)|CUDA_VISIBLE_DEVICES=' \
    "$root/ksc2026" "$root/start-jupyter" "$root/session-controller.py" "$root/jupyter-job.sh"; then
    printf '금지된 runtime 네트워크·설치 또는 static GPU override가 있습니다.\n' >&2
    exit 1
fi

grep -F -- '--gres=gpu:' "$root/session-controller.py" >/dev/null
grep -F -- '"--time=1-00:00:00"' "$root/session-controller.py" >/dev/null
grep -F -- 'c.ServerApp.ip = '\''0.0.0.0'\''' "$root/jupyter-job.sh" >/dev/null
grep -F -- 'autosaveInterval":60' "$root/jupyter-job.sh" >/dev/null
grep -F -- '"defaultViewers":{"markdown":"Markdown Preview"}' "$root/jupyter-job.sh" >/dev/null
grep -F -- "c.ServerApp.default_url = '/lab/tree/\$KSC_LANDING_PAGE'" "$root/jupyter-job.sh" >/dev/null
grep -F -- 'SLURM_JOB_GPUS' "$root/jupyter-job.sh" >/dev/null
grep -F -- '"gpu_index":%s' "$root/jupyter-job.sh" >/dev/null
grep -F -- 'remote_port=$((18880 + 10#$slurm_job_gpus))' "$root/jupyter-job.sh" >/dev/null
grep -F -- '/scratch/hackathon/ksc2026/bin/ksc2026' "$root/session-controller.py" >/dev/null
if rg -n -- 'account[-_]map|instructor-route|--nodelist|--exclude|--exclusive|CUDA_VISIBLE_DEVICES=' \
    "$root/ksc2026" "$root/start-jupyter" "$root/session-controller.py" "$root/jupyter-job.sh"; then
    printf '역할·고정 노드·정적 GPU 설정이 공용 runtime에 남아 있습니다.\n' >&2
    exit 1
fi
printf 'UNIFIED_RUNTIME_TESTS=PASS\n'
