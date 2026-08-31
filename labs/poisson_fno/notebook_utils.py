"""Compact notebook helpers for the KSC 2026 Poisson FNO exercises.

The validation detail lives here so participant-facing notebooks can focus on
the learning sequence instead of presenting a long HDF5 integrity routine.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple

import h5py
import numpy as np
import yaml

from data_validation import validate_poisson_hdf5
from generate_data import PROFILES


def profile_info(lab_dir: str | Path, profile: str) -> Dict[str, object]:
    """Return paths and commands for one supported classroom profile."""

    if profile not in PROFILES:
        raise ValueError(f"지원하지 않는 profile입니다: {profile}")
    root = Path(lab_dir).resolve()
    spec = PROFILES[profile]
    config_name = "config_FNO" if profile == "gh200" else "config_FNO_recovery"
    return {
        "name": profile,
        "dataset_dir": root / spec.output_dir,
        "grid_size": spec.grid_size,
        "max_mode": spec.max_mode,
        "split_sizes": {
            "train": spec.train_samples,
            "val": spec.val_samples,
            "test": spec.test_samples,
        },
        "config_name": config_name,
        "generate_command": [
            sys.executable,
            "generate_data.py",
            "--profile",
            profile,
            "--device",
            "cuda" if profile == "gh200" else "auto",
        ],
        "train_command": [
            sys.executable,
            "train_fno.py",
            "--config-name",
            config_name,
        ],
    }


def _verify_split(
    path: Path,
    *,
    profile: str,
    split: str,
    expected_samples: int,
    expected_grid_size: int,
    expected_max_mode: int,
) -> Tuple[bool, str]:
    if not path.is_file():
        return False, "file missing"
    expected_shape = (
        expected_samples,
        1,
        expected_grid_size,
        expected_grid_size,
    )
    try:
        with h5py.File(path, "r") as handle:
            validate_poisson_hdf5(
                handle,
                str(path),
                expected_profile=profile,
                expected_split=split,
            )
            if tuple(handle["f"].shape) != expected_shape:
                return False, f"unexpected shape: {handle['f'].shape}"
            if int(handle.attrs["max_mode"]) != expected_max_mode:
                return False, (
                    f"max_mode={handle.attrs['max_mode']}, "
                    f"expected={expected_max_mode}"
                )
            residual = float(handle.attrs["max_relative_poisson_residual"])
    except (KeyError, OSError, TypeError, ValueError) as exc:
        return False, str(exc)
    return True, f"verified residual={residual:.3e}"


def verify_profile_dataset(
    lab_dir: str | Path, profile: str
) -> Dict[str, Tuple[bool, str]]:
    """Validate all train/validation/test files for one profile."""

    info = profile_info(lab_dir, profile)
    results: Dict[str, Tuple[bool, str]] = {}
    for split, expected_samples in info["split_sizes"].items():
        path = info["dataset_dir"] / f"{split}.hdf5"
        results[split] = _verify_split(
            path,
            profile=profile,
            split=split,
            expected_samples=expected_samples,
            expected_grid_size=info["grid_size"],
            expected_max_mode=info["max_mode"],
        )
    return results


def ensure_profile_dataset(
    lab_dir: str | Path,
    profile: str,
    *,
    force: bool = False,
    device: str | None = None,
) -> Dict[str, object]:
    """Reuse a verified dataset or regenerate every split and verify again."""

    root = Path(lab_dir).resolve()
    info = profile_info(root, profile)
    checks = verify_profile_dataset(root, profile)
    for split, (valid, detail) in checks.items():
        print(f"{split:5s}: {'VALID' if valid else 'REGENERATE'} - {detail}")

    if force or not all(valid for valid, _ in checks.values()):
        command = list(info["generate_command"])
        if device is not None:
            command[command.index("--device") + 1] = device
        paths = [info["dataset_dir"] / f"{split}.hdf5" for split in checks]
        if force or any(path.exists() for path in paths):
            command.append("--overwrite")
        print("실행:", " ".join(str(part) for part in command))
        subprocess.run(command, cwd=root, check=True)
    else:
        print("검증된 dataset을 재사용합니다.")

    checks_after = verify_profile_dataset(root, profile)
    invalid = {
        split: detail
        for split, (valid, detail) in checks_after.items()
        if not valid
    }
    if invalid:
        raise RuntimeError(f"Dataset 검증 실패: {invalid}")

    for split in checks_after:
        path = info["dataset_dir"] / f"{split}.hdf5"
        print(f"{path.name:10s}: {path.stat().st_size / 2**20:8.1f} MiB")
    return info


def load_field_pair(
    lab_dir: str | Path,
    profile: str,
    *,
    split: str = "test",
    sample_index: int = 0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Load one verified source/solution pair as two 2D arrays."""

    info = profile_info(lab_dir, profile)
    path = info["dataset_dir"] / f"{split}.hdf5"
    valid, detail = verify_profile_dataset(lab_dir, profile)[split]
    if not valid:
        raise RuntimeError(f"{path}: {detail}")
    with h5py.File(path, "r") as handle:
        count = handle["f"].shape[0]
        if not 0 <= sample_index < count:
            raise IndexError(f"sample_index must be in [0, {count})")
        source = np.asarray(handle["f"][sample_index, 0], dtype=np.float32)
        solution = np.asarray(handle["u"][sample_index, 0], dtype=np.float32)
    return source, solution


def assert_ablation_configs_match(
    first: str | Path, second: str | Path
) -> Dict[str, Tuple[object, object]]:
    """Ensure the classroom ablation changes modes and labels only."""

    with Path(first).open(encoding="utf-8") as stream:
        left = yaml.safe_load(stream)
    with Path(second).open(encoding="utf-8") as stream:
        right = yaml.safe_load(stream)

    def flatten(value, prefix=""):
        flattened = {}
        if isinstance(value, dict):
            for key, nested in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                flattened.update(flatten(nested, path))
        else:
            flattened[prefix] = value
        return flattened

    left_flat = flatten(left)
    right_flat = flatten(right)
    all_keys = sorted(set(left_flat) | set(right_flat))
    differences = {
        key: (left_flat.get(key), right_flat.get(key))
        for key in all_keys
        if left_flat.get(key) != right_flat.get(key)
    }
    allowed = {
        "arch.fno.fno_modes",
        "network_dir",
        "custom.experiment_label",
        "custom.metrics_file",
        "custom.candidate_note",
    }
    unexpected = sorted(set(differences) - allowed)
    if unexpected:
        raise AssertionError(f"통제되지 않은 config 차이: {unexpected}")
    if "arch.fno.fno_modes" not in differences:
        raise AssertionError("두 config의 fno_modes가 동일합니다.")
    return differences
