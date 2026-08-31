#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
archive_path="${1:-${repo_root}/dist/ksc2026-gh200-physicsnemo_25.11-arm64.tar}"
sif_path="${2:-${repo_root}/dist/ksc2026-gh200-physicsnemo_25.11-arm64.sif}"

if command -v apptainer >/dev/null 2>&1; then
    container_runtime="apptainer"
elif command -v singularity >/dev/null 2>&1; then
    container_runtime="singularity"
else
    printf 'Apptainer or Singularity is required on the ARM64 SIF build host.\n' >&2
    exit 1
fi

[[ -f "${archive_path}" ]] || {
    printf 'Docker archive not found: %s\n' "${archive_path}" >&2
    exit 1
}

archive_dir="$(cd -- "$(dirname -- "${archive_path}")" && pwd)"
archive_abs="${archive_dir}/$(basename -- "${archive_path}")"

mkdir -p "$(dirname -- "${sif_path}")"
temp_dir="$(mktemp -d)"
trap 'rm -rf -- "${temp_dir}"' EXIT
archive_def="${temp_dir}/Singularity.archive"
archive_link="${temp_dir}/image.tar"
ln -s "${archive_abs}" "${archive_link}"

# Keep the committed runscript/test contract while changing only the bootstrap
# source from the local Docker daemon to the exported Docker archive.
awk -v archive="${archive_link}" '
    /^Bootstrap:/ { print "Bootstrap: docker-archive"; next }
    /^From:/ { print "From: " archive; next }
    { print }
' "${repo_root}/Singularity" > "${archive_def}"

build_options=()
if (( $(id -u) != 0 )); then
    build_options+=(--fakeroot)
fi
"${container_runtime}" build "${build_options[@]}" "${sif_path}" "${archive_def}"
"${container_runtime}" exec "${sif_path}" \
    /opt/nvidia/physicsnemo_env.sh \
    /opt/ksc2026/container/smoke_test.sh --static

if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${sif_path}" > "${sif_path}.sha256"
else
    shasum -a 256 "${sif_path}" > "${sif_path}.sha256"
fi

printf 'SIF image: %s\n' "${sif_path}"
printf 'Validate on a GH200: %s exec --nv %q /opt/nvidia/physicsnemo_env.sh /opt/ksc2026/container/smoke_test.sh --gpu\n' \
    "${container_runtime}" "${sif_path}"
