# Copyright (c) 2024 NVIDIA Corporation. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# KSC 2026 unified GH200 + PhysicsNeMo SIF definition.
#
# Canonical input is the already built local ARM64 Docker image. No package
# installation or download occurs during this conversion. For the recommended
# Docker archive path, use container/build_sif.sh; it changes only Bootstrap
# and From to docker-archive while retaining all sections below.

Bootstrap: docker-daemon
From: ksc2026-gh200-physicsnemo:25.11-arm64

%labels
    org.opencontainers.image.title KSC 2026 GH200 + PhysicsNeMo course
    org.opencontainers.image.version 25.11-arm64
    org.opencontainers.image.source https://github.com/yang926/KSC2026-GH200-PhysicsNeMo-Tutorial
    kr.repro.ksc2026.runtime-compatibility ksc2026-gh200-physicsnemo-25.11-arm64-v1
    kr.repro.ksc2026.runtime-network-required false

%environment
    export KSC_SOURCE_DIR=/opt/ksc2026/course-source
    export KSC_IMAGE_MANIFEST=/etc/ksc2026-image.json
    export NVHPC_ROOT=/opt/nvidia/hpc_sdk/Linux_aarch64/25.5
    export NVPL_ROOT=/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/math_libs/nvpl
    export OPENBLAS_ROOT=/opt/ksc2026/vendor/openblas
    export PATH=/opt/ksc2026/bin:/usr/local/cuda/bin:/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/compilers/bin:${PATH}
    export CPATH=/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/math_libs/nvpl/include:${CPATH}
    export LIBRARY_PATH=/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/math_libs/nvpl/lib:/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/compilers/lib:${LIBRARY_PATH}
    export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/math_libs/nvpl/lib:/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/compilers/lib:/opt/ksc2026/vendor/openblas/lib
    export PIP_NO_INDEX=1
    export PIP_DISABLE_PIP_VERSION_CHECK=1
    export HF_HUB_OFFLINE=1
    export TRANSFORMERS_OFFLINE=1
    export PYTHONDONTWRITEBYTECODE=1
    export PYTHONUNBUFFERED=1

%runscript
    exec /opt/nvidia/physicsnemo_env.sh /opt/ksc2026/container/entrypoint.sh "$@"

%test
    /opt/nvidia/physicsnemo_env.sh /opt/ksc2026/container/smoke_test.sh --static
