#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""행사 전 예행연습에서 나온 실측값을 모아 노트북에 붙여 넣을 표로 출력합니다.

노트북 네 개를 한 번씩 끝까지 실행한 뒤 참가자 작업공간에서 실행하세요.

    python3 tools/collect_dryrun_metrics.py

읽는 파일 (모두 노트북이 자동으로 남깁니다):
    work/gh200/cpu_results_*.json                              01-1
    work/gh200/gpu_results_*.json                              01-2
    labs/projectile/outputs/ksc_projectile/*/run_summary.json  02-1
    labs/poisson_fno/outputs/ksc_fno_*/*/run_summary.json      02-2

각 종류에서 가장 최근 파일 하나를 씁니다. 특정 실행을 고르려면 --run-dir로
결과 폴더를 직접 지정하세요.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

BLANK = "(측정 안 됨)"


def newest(root: Path, pattern: str) -> Path | None:
    matches = sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"# 읽기 실패: {path} ({error})")
        return None


def fmt(value: Any, spec: str = "{:.3f}") -> str:
    if value is None:
        return BLANK
    try:
        return spec.format(float(value))
    except (TypeError, ValueError):
        return str(value)


# ----------------------------------------------------------------- 01-1 CPU
def table_cpu(payload: dict[str, Any] | None) -> str:
    rows: list[tuple[str, str]] = []
    if payload:
        n = payload.get("matrix_size")
        for stack in ("GCC + OpenBLAS", "nvc + NVPL"):
            for threads in (1, 16):
                hit = next(
                    (
                        r
                        for r in payload.get("thread_experiments", [])
                        if r.get("stack") == stack and r.get("threads") == threads
                    ),
                    None,
                )
                rows.append(
                    (
                        f"`N={n}`, {stack}, {threads} thread"
                        + ("s" if threads > 1 else ""),
                        f"{fmt(hit.get('gflops'), '{:.1f}')} GFLOP/s" if hit else BLANK,
                    )
                )
        first = payload.get("first_results", {})
        checksums = [v.get("checksum") for v in first.values() if isinstance(v, dict)]
        if len(checksums) == 2 and all(c is not None for c in checksums):
            lo, hi = sorted(map(abs, checksums))
            rel = abs(hi - lo) / hi if hi else 0.0
            rows.append(("두 구성의 checksum 차이", f"상대 오차 {rel:.1e}"))
        else:
            rows.append(("두 구성의 checksum 차이", BLANK))
        rows.append(("4–6절 전체 실행 시간", "(직접 기입) 분"))
    else:
        rows = [("work/gh200/cpu_results_*.json 없음 — 01-1 노트북 실행 필요", BLANK)]

    out = ["### 01-1 `01_CPU_Compile_and_Tune.ipynb`", "", "| 측정 조건 | 관측값 |", "|---|---|"]
    out += [f"| {a} | {b} |" for a, b in rows]
    return "\n".join(out)


# ----------------------------------------------------------------- 01-2 GPU
BANDWIDTH_RE = re.compile(
    r"(host_to_device_memcpy_(?:ce|sm)|device_to_host_memcpy_(?:ce|sm))"
)


def parse_bandwidth(stdout: str) -> dict[str, str]:
    """nvbandwidth 출력에서 테스트별 대표 수치를 뽑습니다."""
    found: dict[str, str] = {}
    current: str | None = None
    for line in (stdout or "").splitlines():
        match = BANDWIDTH_RE.search(line)
        if match:
            current = match.group(1)
            continue
        if current:
            numbers = re.findall(r"\d+\.\d+", line)
            if numbers:
                found.setdefault(current, numbers[-1])
                current = None
    return found


def table_gpu(payload: dict[str, Any] | None) -> str:
    rows: list[tuple[str, str]] = []
    if payload:
        statuses = payload.get("program_results", {})

        def status(name: str) -> str:
            text = statuses.get(name, "")
            if "result=PASS" in text:
                return "PASS"
            if "result=SKIP" in text:
                return "SKIP"
            return BLANK

        rows.append(
            (
                "`explicit` / `managed-demand` / `managed-prefetch` 결과",
                " / ".join(
                    status(n)
                    for n in ("explicit", "managed-demand", "managed-prefetch")
                ),
            )
        )
        system_text = statuses.get("system", "")
        if "result=SKIP" in system_text:
            path = "SKIP"
        elif "ATS/hardware-coherent" in system_text:
            path = "ATS / hardware-coherent"
        elif system_text:
            path = "HMM / software-coherent"
        else:
            path = BLANK
        rows.append(("시스템 할당 메모리 경로", path))

        bandwidth = parse_bandwidth(payload.get("nvbandwidth_stdout", ""))
        for key in (
            "host_to_device_memcpy_ce",
            "device_to_host_memcpy_ce",
            "host_to_device_memcpy_sm",
            "device_to_host_memcpy_sm",
        ):
            value = bandwidth.get(key)
            rows.append((f"`{key}`", f"{value} GB/s" if value else BLANK))
        rows.append(("이 노트북 전체 실행 시간", "(직접 기입) 분"))
    else:
        rows = [("work/gh200/gpu_results_*.json 없음 — 01-2 노트북 실행 필요", BLANK)]

    out = ["### 01-2 `02_GPU_Memory_Profile.ipynb`", "", "| 측정 항목 | 관측값 |", "|---|---|"]
    out += [f"| {a} | {b} |" for a, b in rows]
    return "\n".join(out)


# ---------------------------------------------------------------- 02-1 PINN
def table_pinn(payload: dict[str, Any] | None) -> str:
    if not payload:
        rows = [("run_summary.json 없음 — 02-1 노트북 실행 필요", BLANK)]
    else:
        train = payload.get("interval_metrics", {}).get("학습 구간", {})
        extra = payload.get("interval_metrics", {}).get("외삽 구간", {})
        ratio = payload.get("extrapolation_over_training_ratio", {})
        rows = [
            (
                "학습 전체 실행 시간",
                f"{fmt(payload.get('train_wall_seconds', 0) / 60.0, '{:.2f}')} 분",
            ),
            (
                "학습 구간 상대 L2 — `x`, `y`",
                f"{fmt(train.get('x_relative_l2'), '{:.2e}')}, "
                f"{fmt(train.get('y_relative_l2'), '{:.2e}')}",
            ),
            (
                "외삽 구간 상대 L2 — `x`, `y`",
                f"{fmt(extra.get('x_relative_l2'), '{:.2e}')}, "
                f"{fmt(extra.get('y_relative_l2'), '{:.2e}')}",
            ),
            (
                "외삽/학습 오차 비율 — `x`, `y`",
                f"{fmt(ratio.get('x'), '{:.2f}')}배, {fmt(ratio.get('y'), '{:.2f}')}배",
            ),
        ]
        rows.append(
            (
                "실행 조건",
                f"v₀={payload.get('initial_speed_m_s')} m/s, "
                f"θ={payload.get('launch_angle_deg')}°, "
                f"{payload.get('max_steps')} step",
            )
        )

    out = ["### 02-1 `01_Projectile_PINN.ipynb`", "", "| 항목 | 관측값 |", "|---|---|"]
    out += [f"| {a} | {b} |" for a, b in rows]
    return "\n".join(out)


# ----------------------------------------------------------------- 02-2 FNO
def table_fno(payload: dict[str, Any] | None) -> str:
    if not payload:
        rows = [("run_summary.json 없음 — 02-2 노트북 실행 필요", BLANK)]
        verdict = ""
    else:
        dataset_min = (payload.get("dataset_wall_seconds") or 0) / 60.0
        train_min = (payload.get("train_wall_seconds") or 0) / 60.0
        peak = payload.get("peak_memory_allocated_bytes")
        rows = [
            ("데이터셋 생성 시간 (최초 1회)", f"{dataset_min:.2f} 분"),
            (
                f"학습 {payload.get('max_steps')} step 실행 시간",
                f"{train_min:.2f} 분",
            ),
            ("학습 전 테스트 상대 L2", fmt(payload.get("relative_l2_before"), "{:.4e}")),
            ("학습 후 테스트 상대 L2", fmt(payload.get("relative_l2_after"), "{:.4e}")),
            ("오차 감소 배수", f"{fmt(payload.get('improvement_factor'), '{:.2f}')}배"),
            (
                "학습 파라미터 수",
                f"{payload['trainable_parameters']:,}"
                if payload.get("trainable_parameters") is not None
                else BLANK,
            ),
            (
                "최대 PyTorch GPU 메모리",
                f"{peak / 2**30:.2f} GiB" if peak else BLANK,
            ),
            (
                "실행 설정",
                f"`{payload.get('profile')}` · {payload.get('grid_size')}² · "
                f"modes {payload.get('fno_modes')}",
            ),
        ]
        total = dataset_min + train_min
        margin = 80 - total
        mark = "OK" if margin >= 20 else ("빠듯함" if margin >= 0 else "초과")
        verdict = (
            f"\n**80분 세션 판정 — {mark}**  "
            f"데이터 생성 {dataset_min:.1f}분 + 학습 {train_min:.1f}분 = "
            f"**{total:.1f}분**. 설명·활동·결과 해석에 남는 시간 {margin:.1f}분.\n"
            "여유가 20분 미만이면 데이터셋을 중앙 게시본에 미리 생성해 넣거나 "
            "`recovery` 프로파일로 진행하세요.\n"
        )

    out = ["### 02-2 `02_Poisson_FNO.ipynb`", "", "| 항목 | 관측값 |", "|---|---|"]
    out += [f"| {a} | {b} |" for a, b in rows]
    return "\n".join(out) + "\n" + verdict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", nargs="?", default=".", help="과정 최상위 폴더 (기본: 현재 폴더)"
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()

    if not (root / "00_Start_Here.ipynb").is_file():
        print(f"과정 최상위 폴더가 아닙니다: {root}")
        return 1

    cpu = read_json(newest(root, "work/gh200/cpu_results_*.json"))
    gpu = read_json(newest(root, "work/gh200/gpu_results_*.json"))
    pinn = read_json(
        newest(root, "labs/projectile/outputs/ksc_projectile/*/run_summary.json")
    )
    fno = read_json(
        newest(root, "labs/poisson_fno/outputs/ksc_fno_*/*/run_summary.json")
    )

    print("# KSC 2026 예행연습 실측값")
    print()
    print("각 노트북의 `## 참고 — 사전 검증에서 관측한 값` 표에 붙여 넣으세요.")
    print(f"\n측정 위치: `{root}`\n")
    print("---\n")
    for block in (table_cpu(cpu), table_gpu(gpu), table_pinn(pinn), table_fno(fno)):
        print(block)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
