#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

mode="${1:---static}"
source_dir="${KSC_SOURCE_DIR:-/opt/ksc2026/course-source}"
manifest="${KSC_IMAGE_MANIFEST:-/etc/ksc2026-image.json}"
course_manifest="${KSC_COURSE_MANIFEST:-/opt/ksc2026/course-manifest.sha256}"
nvhpc_root="${NVHPC_ROOT:-/opt/nvidia/hpc_sdk/Linux_aarch64/25.5}"
nvpl_root="${NVPL_ROOT:-${nvhpc_root}/math_libs/nvpl}"
openblas_root="${OPENBLAS_ROOT:-/opt/ksc2026/vendor/openblas}"

pass() {
    printf '[PASS] %s\n' "$1"
}

fail() {
    printf '[FAIL] %s\n' "$1" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "command not found: $1"
    pass "command: $1"
}

case "$(uname -m)" in
    aarch64|arm64) pass "ARM64 userspace" ;;
    *) fail "expected ARM64 userspace, found $(uname -m)" ;;
esac

for command_name in python3 gcc make nvc nvcc nsys nvbandwidth jupyter-lab readelf; do
    require_command "${command_name}"
done

[[ -f "${manifest}" ]] || fail "image manifest missing: ${manifest}"
[[ -x "${nvhpc_root}/compilers/bin/nvc" ]] || fail "NVHPC 25.5 nvc missing"
[[ -d "${nvpl_root}/include" ]] || fail "NVPL include directory missing"
[[ -d "${nvpl_root}/lib" ]] || fail "NVPL library directory missing"
if [[ ":${LD_LIBRARY_PATH:-}:" == *":${nvhpc_root}/math_libs/lib64:"* ]]; then
    fail "NVHPC CUDA 12.9 math_libs/lib64 must not override the PhysicsNeMo CUDA runtime"
fi
find "${openblas_root}/lib" -maxdepth 1 -name 'libopenblas*' -print -quit \
    | grep --quiet . || fail "OpenBLAS library missing"
pass "NVHPC/NVPL/OpenBLAS roots without CUDA 12.9 runtime override"

nvc -V 2>&1 | grep --quiet '25\.5' || fail "nvc is not NVHPC 25.5"
nvcc --version 2>&1 | grep --quiet 'release 13\.0' || fail "nvcc is not CUDA 13.0"
nsys --version 2>&1 | grep --quiet '2025\.5' || fail "nsys is not Nsight Systems 2025.5"
if readelf -d "$(command -v nvbandwidth)" \
    | grep -Eiq 'NEEDED.*libboost_program_options|RPATH.*\/tmp|RUNPATH.*\/tmp'; then
    fail "nvbandwidth has an unexpected dynamic Boost dependency or build-path RPATH"
fi
pass "nvbandwidth contains statically linked Boost.ProgramOptions"
python3 -c 'import json, os; p=os.environ.get("KSC_IMAGE_MANIFEST", "/etc/ksc2026-image.json"); d=json.load(open(p, encoding="utf-8")); assert d["platform"] == "linux/arm64"; assert d["components"]["physicsnemo"] == "25.11"; assert d["components"]["nvhpc"] == "25.5"; assert d["components"]["nvpl"] == "25.5"; assert d["components"]["boost_program_options"] == "1.83.0 (statically linked into nvbandwidth)"; assert d["components"]["openblas"] == "0.3.31"; assert d["components"]["nvbandwidth"] == "0.8"'
pass "pinned component manifest"

python3 -c 'import physicsnemo, physicsnemo.sym, torch; print("PhysicsNeMo import OK; torch", torch.__version__)'
pass "PhysicsNeMo/PyTorch imports"

[[ -f "${course_manifest}" ]] || fail "course checksum manifest missing"
sha256sum --check --strict --quiet "${course_manifest}" \
    || fail "course payload checksum mismatch"
pass "course payload SHA-256"

for course_file in \
    README.md \
    00_Start_Here.ipynb \
    01_GH200/01_CPU_Compile_and_Tune.ipynb \
    01_GH200/02_GPU_Memory_Profile.ipynb \
    02_PhysicsNeMo/01_Projectile_PINN.ipynb \
    02_PhysicsNeMo/02_Poisson_FNO.ipynb \
    02_PhysicsNeMo/optional/FNO_Mode_Ablation.ipynb; do
    [[ -f "${source_dir}/${course_file}" ]] || fail "course file missing: ${course_file}"
done
[[ -d "${source_dir}/labs/gh200" ]] || fail "GH200 lab support files missing"
[[ -d "${source_dir}/labs/projectile" ]] || fail "Projectile lab support files missing"
[[ -d "${source_dir}/labs/poisson_fno" ]] || fail "FNO lab support files missing"
[[ -d "${source_dir}/operations" ]] || fail "site operations package missing"
[[ -f "${source_dir}/02_PhysicsNeMo/optional/README.md" ]] || fail "PhysicsNeMo optional index missing"
pass "required participant path and lab assets"

for course_image in \
    labs/projectile/images/projectile.svg \
    labs/projectile/images/physicsnemo_sym_workflow.webp \
    labs/poisson_fno/images/fno_data_flow.svg; do
    [[ -s "${source_dir}/${course_image}" ]] || fail "course image missing or empty: ${course_image}"
done
pass "three active course images"

build_dir="$(mktemp -d)"
cleanup() {
    rm -rf -- "${build_dir}"
}
trap cleanup EXIT

make --directory="${source_dir}/labs/gh200/blas" \
    BUILD_DIR="${build_dir}/blas" \
    OPENBLAS_PREFIX="${openblas_root}" \
    all
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
    "${build_dir}/blas/dgemm-openblas" 64 1
OMP_NUM_THREADS=2 \
    "${build_dir}/blas/dgemm-nvpl" 64 1
pass "OpenBLAS and NVPL DGEMM compile/link/run"

nvcc -O2 -arch=sm_90 \
    "${source_dir}/labs/gh200/cuda_memory/explicit.cu" \
    -o "${build_dir}/cuda-explicit"
nvcc -O2 -arch=sm_90 \
    "${source_dir}/labs/gh200/cuda_memory/managed.cu" \
    -o "${build_dir}/cuda-managed"
nvcc -O2 -arch=sm_90 \
    "${source_dir}/labs/gh200/cuda_memory/hmm.cu" \
    -o "${build_dir}/cuda-hmm"
for cuda_binary in cuda-explicit cuda-managed cuda-hmm; do
    [[ -x "${build_dir}/${cuda_binary}" ]] \
        || fail "nvcc did not produce CUDA executable: ${cuda_binary}"
done
pass "three CUDA memory examples compile/link for SM90"

if [[ "${mode}" == "--static" ]]; then
    printf 'Static image smoke test complete. GPU execution was not requested.\n'
    exit 0
fi

[[ "${mode}" == "--gpu" ]] || fail "usage: smoke_test.sh [--static|--gpu]"
require_command nvidia-smi
nvidia-smi --query-gpu=name,compute_cap,driver_version --format=csv,noheader
python3 -c 'import torch; assert torch.cuda.is_available(), "CUDA unavailable: check Apptainer --nv and the host driver"; name=torch.cuda.get_device_name(0); major, minor=torch.cuda.get_device_capability(0); assert "GH200" in name.upper(), f"expected GH200, found {name}"; assert (major, minor) == (9, 0), f"expected GH200 SM90, found {name} SM{major}{minor}"; x=torch.arange(1024, device="cuda", dtype=torch.float32); assert float((x*2).sum().item()) == 1047552.0; torch.cuda.synchronize(); print(name, f"SM{major}{minor}", "CUDA tensor operation PASS")'
pass "CUDA-visible GH200 GPU and CUDA initialization"

driver_version="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits | head -n 1)"
driver_major="${driver_version%%.*}"
[[ "${driver_major}" =~ ^[0-9]+$ ]] && (( driver_major >= 570 )) || fail "host driver R570 or newer is required: ${driver_version}"
if (( driver_major < 580 )); then
    printf '[INFO] Host driver %s passed a CUDA tensor operation through the image CUDA 13 forward-compatibility path.\n' "${driver_version}"
else
    pass "host driver version ${driver_version}"
fi

"${build_dir}/cuda-explicit"
"${build_dir}/cuda-managed"
pass "explicit-copy and UVM examples execute"

nsys profile \
    --trace=cuda \
    --sample=none \
    --force-overwrite=true \
    --output "${build_dir}/cuda-explicit-smoke" \
    "${build_dir}/cuda-explicit"
[[ -s "${build_dir}/cuda-explicit-smoke.nsys-rep" ]] \
    || fail "Nsight Systems report was not created"
pass "Nsight Systems captures a CUDA report"

ldd "$(command -v nvbandwidth)" > "${build_dir}/nvbandwidth.ldd"
if grep --quiet 'not found' "${build_dir}/nvbandwidth.ldd"; then
    cat "${build_dir}/nvbandwidth.ldd" >&2
    fail "nvbandwidth has an unresolved shared-library dependency"
fi
if grep --ignore-case --quiet 'libboost_program_options' "${build_dir}/nvbandwidth.ldd"; then
    cat "${build_dir}/nvbandwidth.ldd" >&2
    fail "nvbandwidth unexpectedly depends on a shared Boost.ProgramOptions library"
fi
pass "nvbandwidth runtime libraries resolve without dynamic Boost"

nvbandwidth -t host_to_device_memcpy_ce device_to_host_memcpy_ce
pass "nvbandwidth host/device copy tests"
printf 'GH200 GPU smoke test complete.\n'
