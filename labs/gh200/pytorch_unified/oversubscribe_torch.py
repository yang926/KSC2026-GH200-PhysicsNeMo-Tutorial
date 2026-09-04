#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""HBM보다 큰 PyTorch 텐서를 기본 할당기와 통합 메모리 할당기로 각각 시도합니다.

PyTorch의 할당기는 CUDA를 처음 사용하기 전에 바꿔야 하므로, 두 조건을 한
프로세스에서 비교할 수 없습니다. 그래서 이 스크립트는 한 번에 한 조건만
실행하고, 노트북이 두 번 호출해 결과를 비교합니다.

    python3 oversubscribe_torch.py --allocator default
    python3 oversubscribe_torch.py --allocator managed

결과는 마지막 줄에 KSC_RESULT= 접두사를 붙인 JSON 한 줄로 출력합니다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
HBM_RATIO = 1.2          # HBM 여유의 몇 배를 요청할지
SYSTEM_SHARE = 0.30      # 시스템 메모리 여유 중 사용할 비율


def gpu_memory_bytes() -> tuple[int, int]:
    """torch를 불러오기 전에 nvidia-smi로 HBM 여유와 전체를 읽습니다."""
    query = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=memory.free,memory.total",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    free_mib, total_mib = (int(v) for v in query.stdout.splitlines()[0].split(","))
    return free_mib * 1024**2, total_mib * 1024**2


def system_available_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("/proc/meminfo에서 MemAvailable을 찾지 못했습니다.")


def build_allocator(build_dir: Path) -> Path:
    """통합 메모리 할당기를 공유 라이브러리로 빌드합니다."""
    build_dir.mkdir(parents=True, exist_ok=True)
    library = build_dir / "managed_alloc.so"
    subprocess.run(
        [
            "nvcc", "-O3", "-shared", "-Xcompiler", "-fPIC",
            "-o", str(library), str(LAB_DIR / "managed_alloc.cu"),
        ],
        check=True,
    )
    return library


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allocator", choices=("default", "managed"), required=True)
    parser.add_argument("--build-dir", default=None, help="공유 라이브러리를 둘 폴더")
    args = parser.parse_args()

    hbm_free, hbm_total = gpu_memory_bytes()
    system_available = system_available_bytes()

    requested = min(
        int(hbm_free * HBM_RATIO),
        int(system_available * SYSTEM_SHARE),
    )
    elements = requested // 4  # float32
    requested = elements * 4
    ready = requested > hbm_free and elements > 0

    summary: dict[str, object] = {
        "allocator": args.allocator,
        "hbm_free_bytes": hbm_free,
        "hbm_total_bytes": hbm_total,
        "system_available_bytes": system_available,
        "requested_bytes": requested,
        "requested_over_hbm_free": requested / hbm_free if hbm_free else None,
        "ready": ready,
    }

    if not ready:
        summary["status"] = "SKIP"
        summary["detail"] = "HBM을 넘기는 크기를 안전하게 만들 수 없습니다."
        print("KSC_RESULT=" + json.dumps(summary, ensure_ascii=False))
        return 0

    # 할당기 교체는 CUDA를 처음 쓰기 전에 해야 합니다.
    if args.allocator == "managed":
        build_dir = Path(args.build_dir) if args.build_dir else LAB_DIR / "build"
        library = build_allocator(build_dir)
        import torch

        allocator = torch.cuda.memory.CUDAPluggableAllocator(
            str(library), "ksc_managed_malloc", "ksc_managed_free"
        )
        torch.cuda.memory.change_current_allocator(allocator)
        summary["allocator_library"] = str(library)
    else:
        import torch

    summary["torch_version"] = torch.__version__
    summary["device_name"] = torch.cuda.get_device_name(0)

    try:
        started = time.perf_counter()
        tensor = torch.empty(elements, dtype=torch.float32, device="cuda")
        tensor.fill_(1.5)
        torch.cuda.synchronize()
        allocate_seconds = time.perf_counter() - started

        started = time.perf_counter()
        tensor.mul_(2.0)
        torch.cuda.synchronize()
        compute_seconds = time.perf_counter() - started

        checked = float(tensor[0].item()), float(tensor[-1].item())
        summary["status"] = "PASS"
        summary["allocate_seconds"] = allocate_seconds
        summary["compute_seconds"] = compute_seconds
        summary["checked_values"] = checked
        summary["correct"] = all(abs(v - 3.0) < 1e-6 for v in checked)
        del tensor
    except torch.cuda.OutOfMemoryError as error:
        summary["status"] = "OOM"
        summary["detail"] = str(error).splitlines()[0]
    except RuntimeError as error:
        summary["status"] = "OOM" if "out of memory" in str(error).lower() else "ERROR"
        summary["detail"] = str(error).splitlines()[0]

    print("KSC_RESULT=" + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
