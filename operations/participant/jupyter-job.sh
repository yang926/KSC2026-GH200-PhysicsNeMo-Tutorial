#!/usr/bin/env bash
# KSC 2026 compute-node payload. Slurm supplies one isolated GH200.

set -Eeuo pipefail
set -f
umask 077

for name in SLURM_JOB_ID KSC_STATE_DIR KSC_WORK_DIR KSC_LOG_DIR KSC_IMAGE KSC_IMAGE_SHA256 \
    KSC_EXPECTED_GPU_COUNT KSC_APPTAINER \
    KSC_COURSE_COMMIT KSC_RUNTIME_COMPATIBILITY KSC_ENTRY_NOTEBOOK KSC_LANDING_PAGE; do
    [[ -n "${!name:-}" ]] || { printf 'KSC2026 compute 오류: %s 값이 없습니다.\n' "$name" >&2; exit 120; }
done

[[ "$SLURM_JOB_ID" =~ ^[1-9][0-9]*$ ]] || exit 121
[[ "$KSC_EXPECTED_GPU_COUNT" == 1 ]] || exit 121
[[ "$KSC_IMAGE_SHA256" =~ ^[0-9a-f]{64}$ && "$KSC_COURSE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || exit 121
[[ "$KSC_STATE_DIR" == "/scratch/$(id -un)/ksc2026/session" ]] || exit 122
[[ "$KSC_WORK_DIR" == "/scratch/$(id -un)/ksc2026/workspaces/course-"* ]] || exit 122
[[ "$KSC_LOG_DIR" == "/scratch/$(id -un)/ksc2026/logs" ]] || exit 122
[[ -d "$KSC_WORK_DIR" && ! -L "$KSC_WORK_DIR" && -w "$KSC_WORK_DIR" ]] || exit 122
[[ -d "$KSC_LOG_DIR" && ! -L "$KSC_LOG_DIR" && -w "$KSC_LOG_DIR" ]] || exit 122
[[ -f "$KSC_IMAGE" && ! -L "$KSC_IMAGE" && -r "$KSC_IMAGE" ]] || exit 123
[[ -x "$KSC_APPTAINER" && ! -L "$KSC_APPTAINER" ]] || exit 123
[[ -f "$KSC_WORK_DIR/$KSC_ENTRY_NOTEBOOK" && ! -L "$KSC_WORK_DIR/$KSC_ENTRY_NOTEBOOK" ]] || exit 123
[[ -f "$KSC_WORK_DIR/$KSC_LANDING_PAGE" && ! -L "$KSC_WORK_DIR/$KSC_LANDING_PAGE" ]] || exit 123
[[ "$KSC_LANDING_PAGE" == "README.md" ]] || exit 123
compute_node="$(hostname -s)"
[[ "$compute_node" =~ ^gpu[0-9]{4}$ ]] || {
    printf 'KSC2026 compute 오류: 계산 노드 이름을 안전하게 확인할 수 없습니다: %s\n' "$compute_node" >&2
    exit 124
}
slurm_job_gpus=${SLURM_JOB_GPUS:-}
[[ "$slurm_job_gpus" =~ ^[0-3]$ ]] || {
    printf 'KSC2026 compute 오류: Slurm이 배정한 GPU 번호를 하나로 확인할 수 없습니다.\n' >&2
    exit 124
}
remote_port=$((18880 + 10#$slurm_job_gpus))
(( remote_port >= 18880 && remote_port <= 18883 )) || exit 124

state_dir=$KSC_STATE_DIR
workspace=$KSC_WORK_DIR
runtime_dir="$state_dir/runtime-$SLURM_JOB_ID"
home_dir="$runtime_dir/home"
token_file="$state_dir/token"
ready_file="$state_dir/ready.json"
log_file="$KSC_LOG_DIR/jupyter-$SLURM_JOB_ID.log"
server_config="$home_dir/.jupyter/jupyter_server_config.py"
settings="$home_dir/.jupyter/lab/user-settings/@jupyterlab/docmanager-extension/plugin.jupyterlab-settings"
child_pid=
child_group_verified=0
job_ready_timeout=${KSC_JOB_READY_TIMEOUT:-900}
[[ "$job_ready_timeout" =~ ^[1-9][0-9]*$ ]] || exit 121

is_own_process_group() {
    local pid=${1:-} pgid
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] && (( pid > 1 )) || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]')" || return 1
    [[ "$pgid" == "$pid" ]]
}

wait_for_own_process_group() {
    local pid=$1 attempt
    for ((attempt=0; attempt<20; attempt++)); do
        is_own_process_group "$pid" && return 0
        kill -0 "$pid" 2>/dev/null || return 1
        sleep 0.1
    done
    return 1
}

mkdir -p "$state_dir"
chmod 700 "$state_dir"
[[ ! -e "$runtime_dir" && ! -L "$runtime_dir" ]] || exit 125
mkdir -m 700 -p "$home_dir/.jupyter/lab/user-settings/@jupyterlab/docmanager-extension" \
    "$home_dir/.config" "$home_dir/.cache/matplotlib" "$home_dir/.local/share/jupyter/runtime" \
    "$home_dir/.ipython"
rm -f -- "$token_file" "$ready_file"

cleanup() {
    local saved=$?
    trap - EXIT INT TERM HUP
    set +e
    rm -f -- "$token_file" "$ready_file"
    if [[ -n "$child_pid" ]] && kill -0 "$child_pid" 2>/dev/null; then
        if [[ "$child_group_verified" == 1 ]] && is_own_process_group "$child_pid"; then
            kill -TERM -- "-$child_pid" 2>/dev/null || true
        else
            printf 'KSC2026 compute 경고: Jupyter process group을 재확인하지 못해 PID만 종료합니다.\n' >&2
            kill -TERM -- "$child_pid" 2>/dev/null || true
        fi
        wait "$child_pid" 2>/dev/null || true
    fi
    [[ -d "$runtime_dir" && ! -L "$runtime_dir" ]] && rm -rf -- "$runtime_dir"
    exit "$saved"
}
trap cleanup EXIT INT TERM HUP

# Slurm/cgroup decides the physical GPU. The launcher never writes a static
# CUDA_VISIBLE_DEVICES value; it only verifies that this job sees one device.
visible_count="$(nvidia-smi -L 2>/dev/null | awk '/^GPU [0-9]+:/{n++} END{print n+0}')"
[[ "$visible_count" == 1 && "${SLURM_GPUS_ON_NODE:-1}" == 1 ]] || {
    printf 'KSC2026 compute 오류: 이 Job에는 GH200 한 개만 보여야 합니다(현재 %s개).\n' "$visible_count" >&2
    exit 126
}

container_home=/opt/ksc2026-runtime-home
declare -a opts=(
    exec --nv --cleanenv
    --home "$home_dir:$container_home"
    --bind "$workspace:/workspace"
    --pwd /workspace
    --env "JUPYTER_CONFIG_DIR=$container_home/.jupyter"
    --env "JUPYTER_RUNTIME_DIR=$container_home/.local/share/jupyter/runtime"
    --env "IPYTHONDIR=$container_home/.ipython"
    --env "MPLCONFIGDIR=$container_home/.cache/matplotlib"
    --env PIP_NO_INDEX=1
    --env HF_HUB_OFFLINE=1
    --env TRANSFORMERS_OFFLINE=1
)

"$KSC_APPTAINER" "${opts[@]}" "$KSC_IMAGE" /opt/nvidia/physicsnemo_env.sh python3 - <<'PY'
import platform
import physicsnemo
import torch

assert platform.machine().lower() in {"aarch64", "arm64"}
assert torch.cuda.is_available() and torch.cuda.device_count() == 1
assert "GH200" in torch.cuda.get_device_name(0).upper()
assert torch.cuda.get_device_capability(0) == (9, 0)
probe = torch.arange(1024, device="cuda", dtype=torch.float32)
assert float((probe * 2).sum().item()) == 1047552.0
torch.cuda.synchronize()
PY

python3 - "$remote_port" <<'PY'
import socket
import sys
s = socket.socket()
s.bind(("0.0.0.0", int(sys.argv[1])))
s.close()
PY

token="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
[[ "$token" =~ ^[0-9a-f]{48}$ ]] || exit 127
printf '%s\n' "$token" >"$token_file"
chmod 600 "$token_file"
printf '%s\n' '{"autosave":true,"autosaveInterval":60,"defaultViewers":{"markdown":"Markdown Preview"}}' >"$settings"
chmod 600 "$settings"
cat >"$server_config" <<EOF
c = get_config()
c.ServerApp.ip = '0.0.0.0'
c.ServerApp.port = $remote_port
c.ServerApp.port_retries = 0
c.ServerApp.root_dir = '/workspace'
c.ServerApp.default_url = '/lab/tree/$KSC_LANDING_PAGE'
c.ServerApp.open_browser = False
c.ServerApp.allow_remote_access = True
c.IdentityProvider.token = '$token'
c.ServerApp.log_level = 'WARN'
EOF
chmod 600 "$server_config"

# An asynchronous command may not open its redirections before the parent shell
# continues.  Create and validate the private log synchronously, then pass an
# already-open descriptor to Jupyter so chmod cannot race log creation.
[[ ! -e "$log_file" && ! -L "$log_file" ]] || exit 125
if ! (
    set -o noclobber
    : >"$log_file"
) 2>/dev/null; then
    printf 'KSC2026 compute 오류: Jupyter 로그 파일을 안전하게 만들지 못했습니다.\n' >&2
    exit 125
fi
[[ -f "$log_file" && ! -L "$log_file" && -O "$log_file" ]] || exit 125
chmod 600 "$log_file"
[[ "$(stat -c '%u:%a:%h' -- "$log_file")" == "$(id -u):600:1" ]] || exit 125
exec 9>>"$log_file"
setsid "$KSC_APPTAINER" "${opts[@]}" "$KSC_IMAGE" /opt/nvidia/physicsnemo_env.sh \
    python3 -m jupyterlab --config "$container_home/.jupyter/jupyter_server_config.py" \
    </dev/null >&9 2>&1 &
child_pid=$!
exec 9>&-
if ! wait_for_own_process_group "$child_pid"; then
    printf 'KSC2026 compute 오류: Jupyter가 독립 process group으로 시작되지 않았습니다.\n' >&2
    kill -TERM -- "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
    child_pid=
    exit 129
fi
child_group_verified=1

ready=0
for ((attempt=0; attempt<job_ready_timeout; attempt++)); do
    kill -0 "$child_pid" 2>/dev/null || break
    if python3 - "$remote_port" 3<<<"$token" <<'PY'
import http.client
import json
import os
import sys
token = os.read(3, 128).decode("ascii").strip()
try:
    conn = http.client.HTTPConnection("127.0.0.1", int(sys.argv[1]), timeout=2)
    conn.request("GET", "/api/status", headers={"Authorization": "token " + token})
    response = conn.getresponse()
    value = json.loads(response.read().decode("utf-8"))
    conn.close()
    raise SystemExit(0 if response.status == 200 and isinstance(value, dict) else 1)
except Exception:
    raise SystemExit(1)
PY
    then
        ready=1
        break
    fi
    sleep 1
done
[[ "$ready" == 1 ]] || { tail -n 30 "$log_file" >&2 || true; exit 128; }

ready_tmp="$ready_file.$SLURM_JOB_ID.tmp"
printf '{"job_id":"%s","node":"%s","port":%s,"gpu_index":%s,"course_commit":"%s"}\n' \
    "$SLURM_JOB_ID" "$compute_node" "$remote_port" "$slurm_job_gpus" \
    "$KSC_COURSE_COMMIT" >"$ready_tmp"
chmod 600 "$ready_tmp"
mv -f -- "$ready_tmp" "$ready_file"

wait "$child_pid"
