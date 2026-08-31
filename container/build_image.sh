#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
image_tag="${1:-ksc2026-gh200-physicsnemo:25.11-arm64}"
archive_path="${2:-${repo_root}/dist/ksc2026-gh200-physicsnemo_25.11-arm64.tar}"

command -v docker >/dev/null 2>&1 || {
    printf 'docker is required on the connected ARM64 build host.\n' >&2
    exit 1
}
docker buildx version >/dev/null 2>&1 || {
    printf 'docker buildx is required.\n' >&2
    exit 1
}

mkdir -p "$(dirname -- "${archive_path}")"

docker buildx build \
    --platform linux/arm64 \
    --load \
    --tag "${image_tag}" \
    "${repo_root}"

architecture="$(docker image inspect --format '{{.Architecture}}' "${image_tag}")"
[[ "${architecture}" == "arm64" ]] || {
    printf 'Expected an arm64 image, found %s.\n' "${architecture}" >&2
    exit 1
}

docker run --rm \
    --platform linux/arm64 \
    --entrypoint /opt/nvidia/physicsnemo_env.sh \
    "${image_tag}" \
    /opt/ksc2026/container/smoke_test.sh --static

docker save --output "${archive_path}" "${image_tag}"

if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${archive_path}" > "${archive_path}.sha256"
else
    shasum -a 256 "${archive_path}" > "${archive_path}.sha256"
fi

printf 'Docker image: %s\n' "${image_tag}"
printf 'Docker archive: %s\n' "${archive_path}"
printf 'Next: ./container/build_sif.sh %q\n' "${archive_path}"
