"""Generate deterministic 2D periodic Poisson datasets for the KSC FNO lab.

The canonical problem is

    -Delta u = f  on [0, 1)^2,

with periodic boundary conditions and a zero-mean solution. Samples are made
in Fourier space, where applying ``-Delta`` is an exact multiplication by
``(2*pi)^2 * (kx^2 + ky^2)``. HDF5 files are written batch by batch so the
GH200 profile does not need to hold the full dataset in memory.

Examples::

    python generate_data.py --profile gh200 --device cuda
    python generate_data.py --profile recovery --device auto

The GH200 sizes are benchmark candidates. They must be timed on the actual
KISTI PILOT system before the class configuration is frozen.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import h5py
import numpy as np
import torch


@dataclass(frozen=True)
class DatasetProfile:
    """Dataset-generation settings for one classroom execution path."""

    name: str
    output_dir: str
    grid_size: int
    max_mode: int
    train_samples: int
    val_samples: int
    test_samples: int
    generation_batch_size: int
    description: str


PROFILES: Dict[str, DatasetProfile] = {
    "recovery": DatasetProfile(
        name="recovery",
        output_dir="datasets/Poisson_Fourier_Recovery",
        grid_size=64,
        max_mode=6,
        train_samples=800,
        val_samples=100,
        test_samples=100,
        generation_batch_size=32,
        description="Short, low-risk recovery path for the KSC hands-on lab.",
    ),
    "gh200": DatasetProfile(
        name="gh200",
        output_dir="datasets/Poisson_Fourier_GH200",
        grid_size=256,
        max_mode=24,
        train_samples=2048,
        val_samples=256,
        test_samples=256,
        generation_batch_size=8,
        description=(
            "KSC GH200 showcase candidate; benchmark on KISTI PILOT before use."
        ),
    ),
}

SPLIT_SEEDS = {"train": 20260826, "val": 20260827, "test": 20260828}
EQUATION = "-Delta u = f"
DOMAIN = "[0,1)^2"
BOUNDARY_CONDITION = "periodic"


def make_unit_square_grid(
    n: int,
    *,
    device: torch.device | str = "cpu",
    dtype: torch.dtype = torch.float32,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Return an ``n x n`` periodic grid on ``[0, 1)^2``.

    ``torch.linspace(0, 1, n)`` repeats the periodic endpoint. ``arange/n``
    contains each periodic sample exactly once.
    """

    if n < 2:
        raise ValueError("grid size must be at least 2")
    coordinates = torch.arange(n, device=device, dtype=dtype) / float(n)
    return torch.meshgrid(coordinates, coordinates, indexing="ij")


def _validate_generation_settings(
    batch_size: int, grid_size: int, max_mode: int
) -> None:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if grid_size < 4:
        raise ValueError("grid_size must be at least 4")
    if max_mode < 1:
        raise ValueError("max_mode must be positive")
    if max_mode >= grid_size // 2:
        raise ValueError(
            "max_mode must be below the Nyquist mode (grid_size // 2)"
        )


@torch.no_grad()
def generate_batch_fourier_series(
    batch_size: int,
    grid_size: int,
    max_mode: int,
    *,
    device: torch.device | str = "cpu",
    generator: Optional[torch.Generator] = None,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Generate a batch of exact spectral ``(f, u)`` Poisson pairs.

    A real Gaussian field is transformed with ``rfft2`` and band-limited to
    ``|kx|, |ky| <= max_mode``. The constant mode is removed, giving the
    periodic Poisson problem a unique zero-mean representative.
    """

    _validate_generation_settings(batch_size, grid_size, max_mode)
    resolved_device = torch.device(device)

    noise = torch.randn(
        batch_size,
        grid_size,
        grid_size,
        device=resolved_device,
        dtype=torch.float32,
        generator=generator,
    )
    u_hat = torch.fft.rfft2(noise, norm="ortho")

    # With d=1/N, fftfreq returns integer cycles over the unit interval.
    kx = torch.fft.fftfreq(
        grid_size, d=1.0 / grid_size, device=resolved_device
    )
    ky = torch.fft.rfftfreq(
        grid_size, d=1.0 / grid_size, device=resolved_device
    )
    kx_grid, ky_grid = torch.meshgrid(kx, ky, indexing="ij")
    mode_squared = kx_grid.square() + ky_grid.square()
    mode_mask = (kx_grid.abs() <= max_mode) & (ky_grid <= max_mode)
    mode_mask[0, 0] = False

    u_hat = u_hat * mode_mask
    laplacian_eigenvalue = (2.0 * math.pi) ** 2 * mode_squared
    f_hat = laplacian_eigenvalue * u_hat

    u = torch.fft.irfft2(
        u_hat, s=(grid_size, grid_size), norm="ortho"
    ).to(torch.float32)
    f = torch.fft.irfft2(
        f_hat, s=(grid_size, grid_size), norm="ortho"
    ).to(torch.float32)
    return f, u


def relative_poisson_residual(f: torch.Tensor, u: torch.Tensor) -> float:
    """Return the largest per-sample relative Poisson residual in a batch."""

    if f.shape != u.shape or f.ndim != 3:
        raise ValueError("f and u must have matching (batch, height, width) shapes")
    height, width = u.shape[-2:]
    if height != width:
        raise ValueError("only square grids are supported")
    u_hat = torch.fft.rfft2(u, norm="ortho")
    kx = torch.fft.fftfreq(height, d=1.0 / height, device=u.device)
    ky = torch.fft.rfftfreq(width, d=1.0 / width, device=u.device)
    kx_grid, ky_grid = torch.meshgrid(kx, ky, indexing="ij")
    reconstructed_f = torch.fft.irfft2(
        (2.0 * math.pi) ** 2
        * (kx_grid.square() + ky_grid.square())
        * u_hat,
        s=(height, width),
        norm="ortho",
    )
    sample_dims = (1, 2)
    denominator = torch.linalg.vector_norm(f, dim=sample_dims)
    if torch.any(denominator == 0):
        raise ValueError("cannot normalize residual for an all-zero source")
    numerator = torch.linalg.vector_norm(reconstructed_f - f, dim=sample_dims)
    return float(torch.max(numerator / denominator))


class RunningMoments:
    """Accumulate scalar moments without retaining generated batches."""

    def __init__(self) -> None:
        self.count = 0
        self.total = 0.0
        self.total_squared = 0.0
        self.minimum = math.inf
        self.maximum = -math.inf

    def update(self, array: np.ndarray) -> None:
        values = np.asarray(array, dtype=np.float64)
        self.count += values.size
        self.total += float(values.sum(dtype=np.float64))
        self.total_squared += float(np.square(values).sum(dtype=np.float64))
        self.minimum = min(self.minimum, float(values.min()))
        self.maximum = max(self.maximum, float(values.max()))

    def as_dict(self) -> Dict[str, float | int]:
        if self.count == 0:
            raise RuntimeError("cannot compute moments for an empty dataset")
        mean = self.total / self.count
        variance = max(self.total_squared / self.count - mean * mean, 0.0)
        return {
            "count": self.count,
            "mean": mean,
            "std": math.sqrt(variance),
            "min": self.minimum,
            "max": self.maximum,
        }


def _resolve_device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "--device cuda was requested, but torch.cuda.is_available() is false"
        )
    return torch.device(requested)


def _compression_value(name: str) -> Optional[str]:
    return None if name == "none" else name


def generate_and_save_dataset(
    filename: str | Path,
    num_samples: int,
    grid_size: int = 64,
    max_mode: int = 6,
    batch_size: int = 32,
    *,
    seed: int = 0,
    device: torch.device | str = "cpu",
    profile_name: str = "custom",
    split_name: str = "unspecified",
    compression: str = "lzf",
    overwrite: bool = False,
    residual_tolerance: float = 2.0e-4,
) -> Dict[str, object]:
    """Stream one split to HDF5 and return serializable metadata."""

    _validate_generation_settings(batch_size, grid_size, max_mode)
    if num_samples < 1:
        raise ValueError("num_samples must be positive")
    if compression not in {"lzf", "gzip", "none"}:
        raise ValueError("compression must be one of: lzf, gzip, none")

    destination = Path(filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to reuse unverified data at {destination}. "
            "Re-run with --overwrite to regenerate it with the fixed solver."
        )

    partial = destination.with_suffix(destination.suffix + ".partial")
    if partial.exists():
        partial.unlink()

    resolved_device = torch.device(device)
    generator = torch.Generator(device=resolved_device)
    generator.manual_seed(seed)
    chunks = (min(batch_size, num_samples), 1, grid_size, grid_size)
    dataset_shape = (num_samples, 1, grid_size, grid_size)
    moments = {"f": RunningMoments(), "u": RunningMoments()}
    maximum_residual = 0.0

    print(
        f"[{split_name}] {num_samples} samples, {grid_size}x{grid_size}, "
        f"max_mode={max_mode}, device={resolved_device}"
    )

    try:
        with h5py.File(partial, "w") as handle:
            dataset_kwargs = {
                "shape": dataset_shape,
                "dtype": np.float32,
                "chunks": chunks,
                "compression": _compression_value(compression),
            }
            f_dataset = handle.create_dataset("f", **dataset_kwargs)
            u_dataset = handle.create_dataset("u", **dataset_kwargs)

            offset = 0
            while offset < num_samples:
                current_batch = min(batch_size, num_samples - offset)
                f_tensor, u_tensor = generate_batch_fourier_series(
                    current_batch,
                    grid_size,
                    max_mode,
                    device=resolved_device,
                    generator=generator,
                )
                batch_residual = relative_poisson_residual(f_tensor, u_tensor)
                maximum_residual = max(maximum_residual, batch_residual)
                if not math.isfinite(batch_residual) or batch_residual > residual_tolerance:
                    raise RuntimeError(
                        "Generated data failed the spectral Poisson residual check: "
                        f"{batch_residual:.3e} > {residual_tolerance:.3e}"
                    )

                f_array = f_tensor.unsqueeze(1).cpu().numpy()
                u_array = u_tensor.unsqueeze(1).cpu().numpy()
                end = offset + current_batch
                f_dataset[offset:end] = f_array
                u_dataset[offset:end] = u_array
                moments["f"].update(f_array)
                moments["u"].update(u_array)
                offset = end
                print(f"  wrote {offset}/{num_samples}")

            statistics = {name: value.as_dict() for name, value in moments.items()}
            attributes = {
                "schema_version": "1.0",
                "problem": "two-dimensional periodic Poisson equation",
                "equation": EQUATION,
                "domain": DOMAIN,
                "boundary_condition": BOUNDARY_CONDITION,
                "zero_mean_solution": True,
                "profile": profile_name,
                "split": split_name,
                "num_samples": num_samples,
                "grid_size": grid_size,
                "max_mode": max_mode,
                "seed": seed,
                "generation_device": str(resolved_device),
                "f_mean": statistics["f"]["mean"],
                "f_std": statistics["f"]["std"],
                "u_mean": statistics["u"]["mean"],
                "u_std": statistics["u"]["std"],
                "max_relative_poisson_residual": maximum_residual,
                "residual_tolerance": residual_tolerance,
            }
            for key, value in attributes.items():
                handle.attrs[key] = value

        os.replace(partial, destination)
    except BaseException:
        if partial.exists():
            partial.unlink()
        raise

    metadata: Dict[str, object] = {
        "file": destination.name,
        "num_samples": num_samples,
        "shape": list(dataset_shape),
        "seed": seed,
        "max_relative_poisson_residual": maximum_residual,
        "residual_tolerance": residual_tolerance,
        "statistics": {name: value.as_dict() for name, value in moments.items()},
    }
    print(f"  saved {destination}; residual={maximum_residual:.3e}")
    return metadata


def compute_statistics(filename: str | Path) -> Tuple[float, float, float, float]:
    """Read normalization statistics, using HDF5 metadata when available."""

    with h5py.File(filename, "r") as handle:
        if all(key in handle.attrs for key in ("f_mean", "f_std", "u_mean", "u_std")):
            values = tuple(
                float(handle.attrs[key])
                for key in ("f_mean", "f_std", "u_mean", "u_std")
            )
        else:
            f_data = handle["f"][:]
            u_data = handle["u"][:]
            values = (
                float(f_data.mean()),
                float(f_data.std()),
                float(u_data.mean()),
                float(u_data.std()),
            )
    return values  # type: ignore[return-value]


def _parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="gh200")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--grid-size", type=int)
    parser.add_argument("--max-mode", type=int)
    parser.add_argument("--train-samples", type=int)
    parser.add_argument("--val-samples", type=int)
    parser.add_argument("--test-samples", type=int)
    parser.add_argument("--batch-size", type=int, dest="generation_batch_size")
    parser.add_argument(
        "--compression", choices=("lzf", "gzip", "none"), default="lzf"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing split files after each new file is fully written.",
    )
    return parser.parse_args(argv)


def _with_overrides(profile: DatasetProfile, args: argparse.Namespace) -> DatasetProfile:
    values = asdict(profile)
    for key in (
        "grid_size",
        "max_mode",
        "train_samples",
        "val_samples",
        "test_samples",
        "generation_batch_size",
    ):
        override = getattr(args, key)
        if override is not None:
            values[key] = override
    if args.output_dir is not None:
        values["output_dir"] = str(args.output_dir)
    return DatasetProfile(**values)


def main(argv: Optional[Iterable[str]] = None) -> None:
    """Generate train/validation/test splits and a machine-readable manifest."""

    args = _parse_args(argv)
    profile = _with_overrides(PROFILES[args.profile], args)
    device = _resolve_device(args.device)
    output_dir = Path(profile.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(f"KSC FNO 데이터셋 설정: {profile.name}")
    print(f"문제: {EQUATION}; 영역={DOMAIN}; 경계조건={BOUNDARY_CONDITION}")
    print(profile.description)
    print("=" * 72)

    split_sizes = {
        "train": profile.train_samples,
        "val": profile.val_samples,
        "test": profile.test_samples,
    }
    split_metadata: Dict[str, object] = {}
    for split_name, sample_count in split_sizes.items():
        split_metadata[split_name] = generate_and_save_dataset(
            output_dir / f"{split_name}.hdf5",
            sample_count,
            profile.grid_size,
            profile.max_mode,
            profile.generation_batch_size,
            seed=SPLIT_SEEDS[split_name],
            device=device,
            profile_name=profile.name,
            split_name=split_name,
            compression=args.compression,
            overwrite=args.overwrite,
        )

    manifest = {
        "schema_version": "1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "generator": Path(__file__).name,
        "equation": EQUATION,
        "domain": DOMAIN,
        "boundary_condition": BOUNDARY_CONDITION,
        "profile": asdict(profile),
        "device": str(device),
        "torch_version": torch.__version__,
        "splits": split_metadata,
        "note": (
            "GH200 설정은 KISTI PILOT에서 시간과 메모리를 확인하기 전까지 후보입니다."
            if profile.name == "gh200"
            else "수업 시간 안에 전체 절차를 실행하기 위한 단축 설정입니다."
        ),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"데이터셋 명세 저장: {manifest_path}")


if __name__ == "__main__":
    main()
