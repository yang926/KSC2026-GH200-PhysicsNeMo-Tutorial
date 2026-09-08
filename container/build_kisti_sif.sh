#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

die() {
    printf '오류: %s\n' "$1" >&2
    exit 1
}

warn() {
    printf '주의: %s\n' "$1" >&2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/.." && pwd -P)"
definition="${script_dir}/Apptainer.kisti.def"
sif_path="${1:-${repo_root}/dist/ksc2026-gh200-physicsnemo_25.11-arm64.sif}"

case "$(uname -m)" in
    aarch64|arm64) ;;
    *) die "이 스크립트는 KISTI ARM64 빌드 호스트에서만 실행합니다(uname -m: $(uname -m))" ;;
esac

command -v apptainer >/dev/null 2>&1 || \
    die "Apptainer를 찾지 못했습니다. KISTI에서는 먼저 'module load apptainer/1.4.5'를 실행하세요"
command -v sha256sum >/dev/null 2>&1 || die "sha256sum을 찾지 못했습니다"
[[ -f "${definition}" ]] || die "정의 파일이 없습니다: ${definition}"

apptainer_version="$(apptainer version 2>&1)"
version_number="$(printf '%s\n' "${apptainer_version}" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1 || true)"
[[ -n "${version_number}" ]] || die "Apptainer 버전을 판별할 수 없습니다: ${apptainer_version}"
version_major="${version_number%%.*}"
version_tail="${version_number#*.}"
version_minor="${version_tail%%.*}"
if (( version_major < 1 || (version_major == 1 && version_minor < 4) )); then
    die "Apptainer 1.4 이상이 필요합니다(현재: ${version_number})"
fi
if [[ "${version_number}" != "1.4.5" ]]; then
    warn "KISTI에서 확인한 버전은 1.4.5입니다. 현재 ${version_number}에서도 빌드를 진행하지만 결과를 별도로 기록하세요"
fi

build_jobs="${KSC_BUILD_JOBS:-12}"
[[ "${build_jobs}" =~ ^[0-9]+$ ]] || die "KSC_BUILD_JOBS는 1~12의 정수여야 합니다"
(( build_jobs >= 1 && build_jobs <= 12 )) || die "로그인 노드 보호를 위해 KSC_BUILD_JOBS는 12를 넘을 수 없습니다"

sif_dir="$(dirname -- "${sif_path}")"
mkdir -p "${sif_dir}"
sif_dir="$(cd -- "${sif_dir}" && pwd -P)"
sif_path="${sif_dir}/$(basename -- "${sif_path}")"
[[ ! -e "${sif_path}" && ! -e "${sif_path}.sha256" ]] || \
    die "출력 이미지 또는 체크섬이 이미 있습니다. 기존 결과를 보존하기 위해 중단합니다: ${sif_path}"

scratch_root="${KSC_BUILD_SCRATCH:-${SCRATCH:-/tmp/${USER:-ksc2026}/ksc2026-apptainer-build}}"
[[ "${scratch_root}" == /* ]] || die "KSC_BUILD_SCRATCH는 절대 경로여야 합니다: ${scratch_root}"
mkdir -p "${scratch_root}/cache" "${scratch_root}/tmp"
chmod 700 "${scratch_root}" "${scratch_root}/cache" "${scratch_root}/tmp" 2>/dev/null || true

scratch_fs="$(stat -f -c %T "${scratch_root}" 2>/dev/null || printf 'unknown')"
case "${scratch_fs}" in
    nfs|nfs4) die "Apptainer 임시 경로가 NFS입니다. 로컬 또는 KISTI가 허용한 스크래치를 KSC_BUILD_SCRATCH로 지정하세요: ${scratch_root}" ;;
    unknown) warn "스크래치 파일시스템 유형을 확인하지 못했습니다: ${scratch_root}" ;;
esac

min_scratch_gib="${KSC_MIN_SCRATCH_GIB:-100}"
[[ "${min_scratch_gib}" =~ ^[0-9]+$ ]] || die "KSC_MIN_SCRATCH_GIB는 정수여야 합니다"
available_kib="$(df -Pk "${scratch_root}" | awk 'NR == 2 {print $4}')"
[[ "${available_kib}" =~ ^[0-9]+$ ]] || die "스크래치 여유 공간을 확인할 수 없습니다: ${scratch_root}"
required_kib=$(( min_scratch_gib * 1024 * 1024 ))
(( available_kib >= required_kib )) || \
    die "스크래치 여유 공간이 ${min_scratch_gib} GiB보다 작습니다: ${scratch_root}"

build_tmp="$(mktemp -d "${scratch_root}/tmp/build.XXXXXXXX")"
publish_partial=""
cleanup() {
    rm -rf -- "${build_tmp}"
    if [[ -n "${publish_partial}" ]]; then
        rm -f -- "${publish_partial}"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

export APPTAINER_CACHEDIR="${scratch_root}/cache"
export APPTAINER_TMPDIR="${build_tmp}"
partial_sif="${build_tmp}/$(basename -- "${sif_path}").partial"

printf 'KISTI ARM64 직접 SIF 빌드\n'
printf '  Apptainer: %s\n' "${apptainer_version}"
printf '  정의 파일: %s\n' "${definition}"
printf '  병렬 작업 수: %s (최대 12)\n' "${build_jobs}"
printf '  캐시: %s\n' "${APPTAINER_CACHEDIR}"
printf '  임시 경로: %s\n' "${APPTAINER_TMPDIR}"
printf '  출력: %s\n' "${sif_path}"

cd "${repo_root}"
if command -v python3 >/dev/null 2>&1 \
    && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    python3 tools/validate_course.py
else
    warn "호스트 Python 3.9 이상이 없어 사전 검사를 건너뜁니다. 빌드한 SIF 안에서 같은 검사를 반드시 실행합니다"
fi
apptainer build \
    --arch arm64 \
    --build-arg "BUILD_JOBS=${build_jobs}" \
    --mksquashfs-args "-processors ${build_jobs}" \
    "${partial_sif}" \
    "${definition}"

apptainer exec "${partial_sif}" \
    /opt/nvidia/physicsnemo_env.sh \
    python3 /opt/ksc2026/course-source/tools/validate_course.py

apptainer exec "${partial_sif}" \
    /opt/nvidia/physicsnemo_env.sh \
    /opt/ksc2026/container/smoke_test.sh --static

publish_partial="${sif_path}.partial.$$"
cp -p -- "${partial_sif}" "${publish_partial}"
mv -- "${publish_partial}" "${sif_path}"
publish_partial=""
sha256sum "${sif_path}" > "${sif_path}.sha256"
sha256sum --check --strict "${sif_path}.sha256"

printf '\nSIF와 체크섬을 만들었습니다.\n'
printf '  %s\n' "${sif_path}"
printf '  %s\n' "${sif_path}.sha256"
printf '\n실제 GH200 계산 노드에서 다음 검사를 실행하세요.\n'
printf 'apptainer exec --nv %q /opt/nvidia/physicsnemo_env.sh /opt/ksc2026/container/smoke_test.sh --gpu\n' \
    "${sif_path}"
