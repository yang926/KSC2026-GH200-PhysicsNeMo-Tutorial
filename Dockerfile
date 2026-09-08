# Copyright (c) 2024 NVIDIA Corporation. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# KSC 2026 unified GH200 + PhysicsNeMo image.
#
# The build host may access NGC and the three pinned source archives below.
# The resulting image performs no package installation or
# source download at participant runtime.

ARG PHYSICSNEMO_IMAGE="nvcr.io/nvidia/physicsnemo/physicsnemo:25.11@sha256:4e7f82e33d886828efd1e4d65236f5e44c96dfbd3d316c58723eff9b9298eda6"
ARG NVHPC_IMAGE="nvcr.io/nvidia/nvhpc:25.5-devel-cuda_multi-ubuntu24.04@sha256:d5b8001ed137d70417454279c46f6dde335337efbbd6742a4b1c103cbf85831b"

# The full NVHPC tree includes the 25.5 compilers and bundled NVPL 25.5.
FROM --platform=linux/arm64 ${NVHPC_IMAGE} AS nvhpc

FROM --platform=linux/arm64 ${PHYSICSNEMO_IMAGE} AS native-tools

ARG BUILD_JOBS="12"
ARG BOOST_VERSION="1.83.0"
ARG BOOST_SHA256="c0685b68dd44cc46574cce86c4e17c0f611b15e195be9848dfd0769a0a207628"
ARG OPENBLAS_VERSION="0.3.31"
ARG OPENBLAS_SHA256="6dd2a63ac9d32643b7cc636eab57bf4e57d0ed1fff926dfbc5d3d97f2d2be3a6"
ARG NVBANDWIDTH_VERSION="0.8"
ARG NVBANDWIDTH_SHA256="b3622945eb7fce2b4e1aea7d13de04f415f4d998db602893201a904320cf2d39"

# The digest-pinned PhysicsNeMo base provides these ARM64 build tools. Keep the
# image build rootless-compatible by validating that contract instead of using
# a distribution package manager.
RUN set -eux; \
    test "$(dpkg --print-architecture)" = "arm64"; \
    case "${BUILD_JOBS}" in ''|*[!0-9]*) exit 1 ;; esac; \
    test "${BUILD_JOBS}" -ge 1; \
    test "${BUILD_JOBS}" -le 12; \
    for tool in ar cmake curl find g++ gcc gzip install make readelf sha256sum tar nvcc; do \
        command -v "${tool}" >/dev/null; \
    done; \
    cmake --version | awk 'NR == 1 { split($3, v, "."); exit !(v[1] > 3 || (v[1] == 3 && v[2] >= 20)) }'

# Build only Boost.ProgramOptions and keep it static inside nvbandwidth.
RUN set -eux; \
    mkdir -p /tmp/boost /tmp/boost-install; \
    curl --fail --location --retry 3 \
        "https://archives.boost.io/release/${BOOST_VERSION}/source/boost_1_83_0.tar.gz" \
        --output /tmp/boost_1_83_0.tar.gz; \
    echo "${BOOST_SHA256}  /tmp/boost_1_83_0.tar.gz" | sha256sum --check --strict -; \
    tar --extract --gzip --file /tmp/boost_1_83_0.tar.gz \
        --directory /tmp/boost --strip-components=1; \
    cd /tmp/boost; \
    ./bootstrap.sh \
        --with-toolset=gcc \
        --with-libraries=program_options \
        --prefix=/tmp/boost-install; \
    ./b2 -j"${BUILD_JOBS}" \
        --with-program_options \
        toolset=gcc \
        variant=release \
        link=static \
        runtime-link=shared \
        threading=multi \
        cxxstd=17 \
        cxxflags=-fPIC \
        --layout=system \
        --prefix=/tmp/boost-install \
        install; \
    test -s /tmp/boost-install/lib/libboost_program_options.a; \
    install -D -m 0644 /tmp/boost/LICENSE_1_0.txt \
        /opt/ksc2026/licenses/Boost-LICENSE_1_0.txt

# Build a pinned, C-only OpenBLAS. DYNAMIC_ARCH selects an appropriate ARM
# kernel on the GH200 Grace CPU; applications may set OPENBLAS_NUM_THREADS.
RUN mkdir -p /tmp/openblas /opt/ksc2026/vendor/openblas \
    && curl --fail --location --retry 3 \
        "https://github.com/OpenMathLib/OpenBLAS/releases/download/v${OPENBLAS_VERSION}/OpenBLAS-${OPENBLAS_VERSION}.tar.gz" \
        --output /tmp/openblas.tar.gz \
    && echo "${OPENBLAS_SHA256}  /tmp/openblas.tar.gz" | sha256sum --check --strict - \
    && tar --extract --gzip --file /tmp/openblas.tar.gz \
        --directory /tmp/openblas --strip-components=1 \
    && make -C /tmp/openblas -j"${BUILD_JOBS}" \
        DYNAMIC_ARCH=1 NOFORTRAN=1 USE_OPENMP=0 \
    && make -C /tmp/openblas \
        DYNAMIC_ARCH=1 NOFORTRAN=1 USE_OPENMP=0 \
        PREFIX=/opt/ksc2026/vendor/openblas install \
    && install -D -m 0644 /tmp/openblas/LICENSE \
        /opt/ksc2026/licenses/OpenBLAS-LICENSE \
    && rm -rf /tmp/openblas /tmp/openblas.tar.gz

# Build nvbandwidth for GH200's Hopper GPU (SM90).
RUN mkdir -p /tmp/nvbandwidth /opt/ksc2026/bin \
    && curl --fail --location --retry 3 \
        "https://github.com/NVIDIA/nvbandwidth/archive/refs/tags/v${NVBANDWIDTH_VERSION}.tar.gz" \
        --output /tmp/nvbandwidth.tar.gz \
    && echo "${NVBANDWIDTH_SHA256}  /tmp/nvbandwidth.tar.gz" | sha256sum --check --strict - \
    && tar --extract --gzip --file /tmp/nvbandwidth.tar.gz \
        --directory /tmp/nvbandwidth --strip-components=1 \
    && cuda_stub="$(find -L /usr/local/cuda -path '*/stubs/libcuda.so' -print -quit)" \
    && test -n "${cuda_stub}" \
    && cuda_stub_dir="$(dirname "${cuda_stub}")" \
    && test -f "${cuda_stub_dir}/libnvidia-ml.so" \
    && cmake -S /tmp/nvbandwidth -B /tmp/nvbandwidth/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CUDA_ARCHITECTURES=90 \
        -DMULTINODE=OFF \
        -DBOOST_ROOT=/tmp/boost-install \
        -DBoost_ROOT=/tmp/boost-install \
        -DBOOST_LIBRARYDIR=/tmp/boost-install/lib \
        -DBoost_NO_SYSTEM_PATHS=ON \
        -DBoost_NO_BOOST_CMAKE=ON \
        -DBoost_USE_STATIC_LIBS=ON \
        -DBoost_USE_STATIC_RUNTIME=OFF \
        -DCMAKE_PREFIX_PATH=/tmp/boost-install \
        -DCMAKE_EXE_LINKER_FLAGS="-L${cuda_stub_dir}" \
    && cmake --build /tmp/nvbandwidth/build --parallel "${BUILD_JOBS}" \
    && test -f /tmp/nvbandwidth/build/CMakeFiles/nvbandwidth.dir/link.txt \
    && grep --fixed-strings --quiet \
        /tmp/boost-install/lib/libboost_program_options.a \
        /tmp/nvbandwidth/build/CMakeFiles/nvbandwidth.dir/link.txt \
    && install -D -m 0755 /tmp/nvbandwidth/build/nvbandwidth \
        /opt/ksc2026/bin/nvbandwidth \
    && install -D -m 0644 /tmp/nvbandwidth/LICENSE \
        /opt/ksc2026/licenses/nvbandwidth-LICENSE \
    && install -D -m 0644 /tmp/nvbandwidth/Licenses.txt \
        /opt/ksc2026/licenses/nvbandwidth-Licenses.txt \
    && ! readelf -d /opt/ksc2026/bin/nvbandwidth \
        | grep -Eiq 'NEEDED.*libboost_program_options|RPATH.*\/tmp|RUNPATH.*\/tmp' \
    && rm -rf \
        /tmp/boost /tmp/boost-install /tmp/boost_1_83_0.tar.gz \
        /tmp/nvbandwidth /tmp/nvbandwidth.tar.gz

FROM --platform=linux/arm64 ${PHYSICSNEMO_IMAGE} AS runtime

ARG OPENBLAS_VERSION="0.3.31"
ARG NVBANDWIDTH_VERSION="0.8"
ARG BOOST_VERSION="1.83.0"

LABEL org.opencontainers.image.title="KSC 2026 GH200 + PhysicsNeMo course" \
      org.opencontainers.image.description="Offline ARM64 course image with PhysicsNeMo, NVHPC/NVPL, OpenBLAS, nvbandwidth, Nsight Systems, CUDA, and JupyterLab" \
      org.opencontainers.image.version="25.11-arm64" \
      org.opencontainers.image.source="https://github.com/yang926/KSC2026-GH200-PhysicsNeMo-Tutorial" \
      kr.repro.ksc2026.runtime-compatibility="ksc2026-gh200-physicsnemo-25.11-arm64-v1" \
      kr.repro.ksc2026.physicsnemo.version="25.11" \
      kr.repro.ksc2026.nvhpc.version="25.5" \
      kr.repro.ksc2026.nvpl.version="25.5" \
      kr.repro.ksc2026.boost-program-options.version="${BOOST_VERSION}-static" \
      kr.repro.ksc2026.openblas.version="${OPENBLAS_VERSION}" \
      kr.repro.ksc2026.nvbandwidth.version="${NVBANDWIDTH_VERSION}" \
      kr.repro.ksc2026.runtime-network-required="false"

# Recheck the participant-facing commands supplied by the pinned base image.
RUN set -eux; \
    test "$(dpkg --print-architecture)" = "arm64"; \
    for tool in gcc make nvcc nsys jupyter-lab; do command -v "${tool}" >/dev/null; done; \
    ldconfig -p | grep --quiet 'libnuma\.so\.1'

COPY --from=nvhpc /opt/nvidia/hpc_sdk /opt/nvidia/hpc_sdk
COPY --from=native-tools /opt/ksc2026 /opt/ksc2026

ENV KSC_SOURCE_DIR="/opt/ksc2026/course-source" \
    KSC_IMAGE_MANIFEST="/etc/ksc2026-image.json" \
    NVHPC_ROOT="/opt/nvidia/hpc_sdk/Linux_aarch64/25.5" \
    NVPL_ROOT="/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/math_libs/nvpl" \
    OPENBLAS_ROOT="/opt/ksc2026/vendor/openblas" \
    PATH="/opt/ksc2026/bin:/usr/local/cuda/bin:/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/compilers/bin:${PATH}" \
    CPATH="/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/math_libs/nvpl/include:${CPATH}" \
    LIBRARY_PATH="/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/math_libs/nvpl/lib:/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/compilers/lib:${LIBRARY_PATH}" \
    LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/math_libs/nvpl/lib:/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/compilers/lib:/opt/ksc2026/vendor/openblas/lib" \
    PIP_NO_INDEX="1" \
    PIP_DISABLE_PIP_VERSION_CHECK="1" \
    HF_HUB_OFFLINE="1" \
    TRANSFORMERS_OFFLINE="1" \
    PYTHONDONTWRITEBYTECODE="1" \
    PYTHONUNBUFFERED="1"

# .dockerignore is an allow-list. Private GH200 repository artifacts are not
# part of this build context or copied into the course image.
COPY . /opt/ksc2026/course-source
COPY container/ksc2026-image.json /etc/ksc2026-image.json
COPY container/third-party-sources.json /opt/ksc2026/third-party-sources.json
COPY container/entrypoint.sh container/smoke_test.sh /opt/ksc2026/container/

RUN chmod 0755 \
        /opt/ksc2026/container/entrypoint.sh \
        /opt/ksc2026/container/smoke_test.sh \
    && test -x "${NVHPC_ROOT}/compilers/bin/nvc" \
    && test -d "${NVPL_ROOT}/include" \
    && test -d "${NVPL_ROOT}/lib" \
    && command -v gcc >/dev/null \
    && command -v nvcc >/dev/null \
    && command -v nsys >/dev/null \
    && command -v jupyter-lab >/dev/null \
    && command -v nvbandwidth >/dev/null \
    && python3 -c 'import physicsnemo, physicsnemo.sym, torch' \
    && find /opt/ksc2026/course-source -type f -print0 \
        | sort -z \
        | xargs -0 sha256sum \
        > /opt/ksc2026/course-manifest.sha256 \
    && python3 /opt/ksc2026/course-source/tools/validate_course.py \
    && /opt/ksc2026/container/smoke_test.sh --static

WORKDIR /opt/ksc2026/course-source
EXPOSE 8888

ENTRYPOINT ["/opt/nvidia/physicsnemo_env.sh", "/opt/ksc2026/container/entrypoint.sh"]
CMD []
