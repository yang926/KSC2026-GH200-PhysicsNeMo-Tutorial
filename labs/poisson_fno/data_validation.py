"""Pure HDF5 validation shared by training code and classroom notebooks."""

from __future__ import annotations

import math

import h5py


EXPECTED_EQUATION = "-Delta u = f"
MAX_ACCEPTABLE_RESIDUAL = 2.0e-4


def validate_poisson_hdf5(
    handle: h5py.File,
    filename: str,
    *,
    expected_profile: str,
    expected_split: str,
) -> None:
    """Reject legacy or malformed datasets before they enter training."""

    for key in ("f", "u"):
        if key not in handle:
            raise ValueError(f"{filename} does not contain the '{key}' dataset")
    if handle["f"].shape != handle["u"].shape:
        raise ValueError(f"f/u shape mismatch in {filename}")
    if len(handle["f"].shape) != 4 or handle["f"].shape[1] != 1:
        raise ValueError(
            f"Expected (samples, 1, height, width) arrays in {filename}; "
            f"found {handle['f'].shape}"
        )

    required_attributes = (
        "schema_version",
        "equation",
        "boundary_condition",
        "profile",
        "split",
        "num_samples",
        "grid_size",
        "max_relative_poisson_residual",
        "residual_tolerance",
    )
    missing = [name for name in required_attributes if name not in handle.attrs]
    if missing:
        raise ValueError(
            f"{filename} is an unverified legacy dataset (missing {missing}). "
            "Regenerate it with generate_data.py before training."
        )
    if str(handle.attrs["equation"]) != EXPECTED_EQUATION:
        raise ValueError(
            f"Unexpected equation metadata in {filename}: "
            f"{handle.attrs['equation']!r}"
        )
    if str(handle.attrs["boundary_condition"]) != "periodic":
        raise ValueError(f"Expected periodic boundary conditions in {filename}")
    if str(handle.attrs["profile"]) != expected_profile:
        raise ValueError(
            f"Expected profile {expected_profile!r} in {filename}, found "
            f"{handle.attrs['profile']!r}"
        )
    if str(handle.attrs["split"]) != expected_split:
        raise ValueError(
            f"Expected split {expected_split!r} in {filename}, found "
            f"{handle.attrs['split']!r}"
        )
    if int(handle.attrs["num_samples"]) != handle["f"].shape[0]:
        raise ValueError(f"num_samples metadata does not match {filename}")
    if int(handle.attrs["grid_size"]) != handle["f"].shape[-1]:
        raise ValueError(f"grid_size metadata does not match {filename}")

    residual = float(handle.attrs["max_relative_poisson_residual"])
    tolerance = min(
        float(handle.attrs["residual_tolerance"]), MAX_ACCEPTABLE_RESIDUAL
    )
    if not math.isfinite(residual) or residual > tolerance:
        raise ValueError(
            f"Poisson residual verification failed for {filename}: "
            f"{residual:.3e} > {tolerance:.3e}"
        )
