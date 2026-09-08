# SPDX-License-Identifier: Apache-2.0
"""Small, dependency-free helpers for the KSC 2026 GH200 notebook."""

from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def find_repo_root(start: Path | None = None) -> Path:
    """Find the course root without assuming where Jupyter was launched."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "00_Start_Here.ipynb").is_file() and (
            candidate / "labs" / "gh200"
        ).is_dir():
            return candidate
    raise FileNotFoundError(
        "KSC 2026 course root를 찾지 못했습니다. 이미지의 참가자 작업 폴더에서 notebook을 여세요."
    )


def command_text(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    """Run one command, stream captured output, and fail with useful context."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update({key: str(value) for key, value in env.items()})

    print(f"$ {command_text(command)}")
    completed = subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout.rstrip())
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed with exit code {completed.returncode}: {command_text(command)}"
        )
    return completed


def tool_status(names: Iterable[str]) -> dict[str, str | None]:
    return {name: shutil.which(name) for name in names}


def print_tool_status(names: Iterable[str]) -> bool:
    status = tool_status(names)
    for name, path in status.items():
        print(f"{'PASS' if path else 'FAIL':4s}  {name:12s} {path or 'not found'}")
    return all(status.values())


def system_summary() -> dict[str, object]:
    summary: dict[str, object] = {
        "architecture": platform.machine(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
    }
    gpu_query = shutil.which("nvidia-smi")
    if gpu_query:
        result = subprocess.run(
            [
                gpu_query,
                "--query-gpu=name,compute_cap,memory.total",
                "--format=csv,noheader",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        summary["gpu"] = result.stdout.strip() if result.returncode == 0 else "query failed"
    else:
        summary["gpu"] = "nvidia-smi not found"
    return summary


def read_image_manifest() -> dict[str, object] | None:
    for path in (
        Path("/etc/ksc2026-image.json"),
        find_repo_root() / "container" / "ksc2026-image.json",
    ):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    return None
