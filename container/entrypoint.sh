#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

source_dir="${KSC_SOURCE_DIR:-/opt/ksc2026/course-source}"
default_home="${HOME:-/tmp}"
work_dir="${KSC_WORKDIR:-${default_home}/ksc2026-course}"
jupyter_ip="${KSC_JUPYTER_IP:-0.0.0.0}"
jupyter_port="${KSC_JUPYTER_PORT:-8888}"
jupyter_token="${KSC_JUPYTER_TOKEN:-}"
jupyter_root="${KSC_JUPYTER_ROOT:-.}"

if [[ ! -d "${source_dir}" ]]; then
    printf 'KSC source directory is missing: %s\n' "${source_dir}" >&2
    exit 1
fi

# SIF layers are read-only. Seed only missing files into a participant-owned
# directory so reruns preserve notebook edits, checkpoints, and generated data.
if [[ "${KSC_SKIP_SEED:-0}" != "1" ]]; then
    mkdir -p "${work_dir}"
    if [[ "${source_dir%/}" != "${work_dir%/}" ]]; then
        cp -a -n "${source_dir}/." "${work_dir}/"
    fi
    cd "${work_dir}"
else
    cd "${source_dir}"
fi

if (( $# == 0 )); then
    jupyter_args=(
        jupyter-lab
        --no-browser \
        --allow-root \
        "--ip=${jupyter_ip}" \
        "--port=${jupyter_port}" \
        "--ServerApp.port_retries=0" \
        "--ServerApp.root_dir=${jupyter_root}"
    )
    if [[ -n "${jupyter_token}" ]]; then
        jupyter_args+=("--IdentityProvider.token=${jupyter_token}")
    fi
    set -- "${jupyter_args[@]}"
fi

exec "$@"
