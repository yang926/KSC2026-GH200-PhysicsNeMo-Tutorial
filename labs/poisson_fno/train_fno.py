"""Train a PhysicsNeMo-Sym FNO for the KSC periodic Poisson exercise.

Canonical problem::

    -Delta u = f  on [0, 1)^2, with periodic boundary conditions.

The default Hydra config is the GH200 showcase candidate. Use the recovery
profile with::

    python train_fno.py --config-name config_FNO_recovery

This follows NVIDIA's PhysicsNeMo-Sym Darcy FNO pattern: ``DictGridDataset``,
decoder construction, FNO construction, a supervised grid constraint, and a
grid validator. The validation split is used while training. The held-out test
split is evaluated once before training and once after ``Solver.solve()`` to
show the change caused by training; neither evaluation updates the weights.
Final metrics describe the in-memory state after ``solve()`` and are not
labelled as a "best checkpoint".
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

import h5py
import numpy as np
import torch
from hydra.utils import to_absolute_path

import physicsnemo.sym
from physicsnemo.sym.dataset import DictGridDataset
from physicsnemo.sym.domain import Domain
from physicsnemo.sym.domain.constraint import SupervisedGridConstraint
from physicsnemo.sym.domain.validator import GridValidator
from physicsnemo.sym.hydra import PhysicsNeMoConfig, instantiate_arch
from physicsnemo.sym.key import Key
from physicsnemo.sym.solver import Solver
from physicsnemo.sym.utils.io.plotter import GridValidatorPlotter

from data_validation import EXPECTED_EQUATION, validate_poisson_hdf5

def load_dataset(
    filename: str, *, expected_profile: str, expected_split: str
) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """Load and validate one generated Poisson HDF5 split."""

    if not os.path.exists(filename):
        raise FileNotFoundError(
            f"Dataset not found: {filename}\n"
            "Generate it first with 'python generate_data.py --profile gh200 "
            "--device cuda' (or the recovery profile)."
        )
    with h5py.File(filename, "r") as handle:
        validate_poisson_hdf5(
            handle,
            filename,
            expected_profile=expected_profile,
            expected_split=expected_split,
        )
        f_data = np.asarray(handle["f"][:], dtype=np.float32)
        u_data = np.asarray(handle["u"][:], dtype=np.float32)
    return {"f": f_data}, {"u": u_data}


def _normalization_scales(
    invar_train: Dict[str, np.ndarray], outvar_train: Dict[str, np.ndarray]
) -> Dict[str, Tuple[float, float]]:
    """Compute scalar normalization exclusively from the training split."""

    scales: Dict[str, Tuple[float, float]] = {}
    for key, array in (("f", invar_train["f"]), ("u", outvar_train["u"])):
        mean = float(np.mean(array, dtype=np.float64))
        std = float(np.std(array, dtype=np.float64))
        if not math.isfinite(mean) or not math.isfinite(std) or std <= 0.0:
            raise ValueError(
                f"Invalid {key} normalization statistics: mean={mean}, std={std}"
            )
        scales[key] = (mean, std)
    return scales


@torch.no_grad()
def evaluate_held_out_test(
    model: torch.nn.Module,
    invar_test: Dict[str, np.ndarray],
    outvar_test: Dict[str, np.ndarray],
    batch_size: int,
) -> Dict[str, float | int]:
    """Evaluate the final in-memory model state in bounded GPU batches."""

    if batch_size < 1:
        raise ValueError("test batch size must be positive")
    device = next(model.parameters()).device
    source = invar_test["f"]
    target = outvar_test["u"]
    sample_count = source.shape[0]
    element_count = 0
    squared_error = 0.0
    absolute_error = 0.0
    squared_target = 0.0

    was_training = model.training
    model.eval()
    for start in range(0, sample_count, batch_size):
        end = min(start + batch_size, sample_count)
        f_batch = torch.from_numpy(source[start:end]).to(device=device)
        u_true = torch.from_numpy(target[start:end]).to(device=device)
        u_pred = model({"f": f_batch})["u"]
        difference = u_pred - u_true
        squared_error += float(torch.sum(difference.square()).item())
        absolute_error += float(torch.sum(difference.abs()).item())
        squared_target += float(torch.sum(u_true.square()).item())
        element_count += difference.numel()
    if was_training:
        model.train()

    rmse = math.sqrt(squared_error / element_count)
    mae = absolute_error / element_count
    relative_l2 = math.sqrt(squared_error / squared_target)
    return {
        "test_samples": int(sample_count),
        "test_elements": int(element_count),
        "rmse": rmse,
        "mae": mae,
        "relative_l2": relative_l2,
    }


def _write_metrics(path: str, payload: Dict[str, object]) -> None:
    destination = Path(to_absolute_path(path))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.replace(temporary, destination)
    print(f"최종 상태 테스트 지표 저장: {destination}")


@torch.no_grad()
def _save_test_example(
    model: torch.nn.Module,
    invar_test: Dict[str, np.ndarray],
    outvar_test: Dict[str, np.ndarray],
    path: str | Path,
    sample_index: int,
) -> Dict[str, float | int | str]:
    """Save a four-panel held-out test example and return sample metadata."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sample_count = int(invar_test["f"].shape[0])
    if not 0 <= sample_index < sample_count:
        raise IndexError(
            f"test_example_index must be in [0, {sample_count}), got {sample_index}"
        )

    device = next(model.parameters()).device
    source = torch.from_numpy(
        invar_test["f"][sample_index : sample_index + 1]
    ).to(device=device)
    target = outvar_test["u"][sample_index, 0]

    was_training = model.training
    model.eval()
    prediction = model({"f": source})["u"][0, 0].detach().cpu().numpy()
    if was_training:
        model.train()

    source_field = invar_test["f"][sample_index, 0]
    absolute_error = np.abs(prediction - target)
    denominator = float(np.linalg.norm(target))
    sample_relative_l2 = float(np.linalg.norm(prediction - target) / denominator)

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 4, figsize=(15, 3.6), constrained_layout=True)
    fields = (source_field, target, prediction, absolute_error)
    # 그림 안의 글자는 영문으로 둡니다. 교육용 SIF의 matplotlib에는 한글 글꼴이
    # 없어 한글 라벨이 네모로 깨집니다. 설명은 노트북 마크다운에 한국어로 있습니다.
    titles = (
        "f  (source)",
        "u  (ground truth)",
        "u_pred  (prediction)",
        "|u_pred - u|  (absolute error)",
    )
    for index, (axis, field, title) in enumerate(zip(axes, fields, titles)):
        image = axis.imshow(
            field,
            origin="lower",
            cmap="magma" if index == 3 else "coolwarm",
        )
        axis.set_title(title)
        axis.set_xlabel("grid x")
        axis.set_ylabel("grid y")
        figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.suptitle(
        f"test sample {sample_index} · relative L2 = {sample_relative_l2:.3e}",
        fontsize=12,
    )
    figure.savefig(destination, dpi=150, bbox_inches="tight")
    plt.close(figure)
    print(f"테스트 표본 그림 저장: {destination}")
    return {
        "path": str(destination),
        "sample_index": sample_index,
        "sample_relative_l2": sample_relative_l2,
    }


@physicsnemo.sym.main(config_path="conf", config_name="config_FNO")
def run(cfg: PhysicsNeMoConfig) -> None:
    """Build the FNO and compare held-out test metrics before and after training."""

    # PhysicsNeMo writes checkpoints and validators relative to network_dir.
    # Resolve it against Hydra's original working directory so outputs stay
    # beside the metrics file even if Hydra changes the process directory.
    cfg.network_dir = to_absolute_path(str(cfg.network_dir))

    # Keep the classroom comparison reproducible at the configuration level.
    # CUDA kernels may still introduce small run-to-run numerical differences.
    random_seed = int(cfg.custom.random_seed)
    np.random.seed(random_seed)
    torch.manual_seed(random_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(random_seed)

    train_file = to_absolute_path(str(cfg.custom.train_file))
    validation_file = to_absolute_path(str(cfg.custom.validation_file))
    test_file = to_absolute_path(str(cfg.custom.test_file))

    profile = str(cfg.custom.profile)
    invar_train, outvar_train = load_dataset(
        train_file, expected_profile=profile, expected_split="train"
    )
    invar_validation, outvar_validation = load_dataset(
        validation_file, expected_profile=profile, expected_split="val"
    )
    invar_test, outvar_test = load_dataset(
        test_file, expected_profile=profile, expected_split="test"
    )
    test_example_index = int(cfg.custom.test_example_index)
    test_sample_count = int(invar_test["f"].shape[0])
    if not 0 <= test_example_index < test_sample_count:
        raise ValueError(
            "custom.test_example_index must be in "
            f"[0, {test_sample_count}), got {test_example_index}"
        )

    grid_shapes = {
        tuple(invar_train["f"].shape[2:]),
        tuple(invar_validation["f"].shape[2:]),
        tuple(invar_test["f"].shape[2:]),
    }
    if len(grid_shapes) != 1:
        raise ValueError(f"Train/validation/test grids do not match: {grid_shapes}")

    scales = _normalization_scales(invar_train, outvar_train)
    input_keys = [Key("f", scale=scales["f"])]
    output_keys = [Key("u", scale=scales["u"])]

    train_dataset = DictGridDataset(invar_train, outvar_train)
    validation_dataset = DictGridDataset(invar_validation, outvar_validation)

    decoder_net = instantiate_arch(cfg=cfg.arch.decoder, output_keys=output_keys)
    fno = instantiate_arch(
        cfg=cfg.arch.fno,
        input_keys=input_keys,
        decoder_net=decoder_net,
    )
    nodes = [fno.make_node("fno")]
    trainable_parameters = int(
        sum(parameter.numel() for parameter in fno.parameters() if parameter.requires_grad)
    )

    print("=" * 72)
    print(f"KSC FNO 실행 설정: {cfg.custom.profile}")
    print(f"실험 이름: {cfg.custom.experiment_label}")
    print(f"난수 시드: {random_seed}")
    print(f"결과 폴더: {cfg.network_dir}")
    print(f"문제: {EXPECTED_EQUATION}; 주기적 경계조건")
    print(f"격자: {next(iter(grid_shapes))}")
    print(f"학습 파라미터 수: {trainable_parameters:,}")
    print(
        "데이터 분할: "
        f"학습={invar_train['f'].shape[0]}, "
        f"검증={invar_validation['f'].shape[0]}, "
        f"테스트={invar_test['f'].shape[0]}"
    )
    print(
        "학습 데이터 기준 정규화: "
        f"f(mean={scales['f'][0]:.3e}, std={scales['f'][1]:.3e}), "
        f"u(mean={scales['u'][0]:.3e}, std={scales['u'][1]:.3e})"
    )
    print("=" * 72)

    domain = Domain()
    supervised = SupervisedGridConstraint(
        nodes=nodes,
        dataset=train_dataset,
        batch_size=cfg.batch_size.grid,
    )
    domain.add_constraint(supervised, "train_supervised")

    validator = GridValidator(
        nodes,
        dataset=validation_dataset,
        batch_size=cfg.batch_size.validation,
        plotter=GridValidatorPlotter(n_examples=3),
    )
    domain.add_validator(validator, "validation")

    # Record the randomly initialized model once so the notebook can show what
    # training changed. This uses the held-out test split for observation only;
    # no gradient or weight update is performed.
    metrics_before_training = evaluate_held_out_test(
        fno,
        invar_test,
        outvar_test,
        batch_size=int(cfg.batch_size.test),
    )

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    solver = Solver(cfg, domain)
    solver.solve()

    # Evaluate the held-out test split using the model state that remains after
    # solve(). No checkpoint is selected or loaded here, so this is not a claim
    # about the best validation checkpoint.
    metrics_after_training = evaluate_held_out_test(
        fno,
        invar_test,
        outvar_test,
        batch_size=int(cfg.batch_size.test),
    )
    peak_memory_allocated_bytes = (
        int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else None
    )
    metrics_destination = Path(to_absolute_path(str(cfg.custom.metrics_file)))
    test_example = _save_test_example(
        fno,
        invar_test,
        outvar_test,
        metrics_destination.parent / "held_out_test_example.png",
        test_example_index,
    )
    payload: Dict[str, object] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "profile": str(cfg.custom.profile),
        "experiment_label": str(cfg.custom.experiment_label),
        "random_seed": random_seed,
        "problem": EXPECTED_EQUATION,
        "boundary_condition": "periodic",
        "evaluation_state": "final in-memory state after Solver.solve()",
        "checkpoint_selection": "none",
        "max_steps_configured": int(cfg.training.max_steps),
        "dataset_files": {
            "train": train_file,
            "validation": validation_file,
            "test": test_file,
        },
        "normalization_from_train_only": {
            "f": {"mean": scales["f"][0], "std": scales["f"][1]},
            "u": {"mean": scales["u"][0], "std": scales["u"][1]},
        },
        "model": {
            "fno_modes": int(cfg.arch.fno.fno_modes),
            "nr_fno_layers": int(cfg.arch.fno.nr_fno_layers),
            "decoder_layer_size": int(cfg.arch.decoder.layer_size),
            "train_batch_size": int(cfg.batch_size.grid),
            "trainable_parameters": trainable_parameters,
        },
        "runtime_observation": {
            "peak_memory_allocated_bytes": peak_memory_allocated_bytes,
            "scope": "PyTorch peak allocated memory for this process; not total GPU usage",
        },
        "metrics_before_training": metrics_before_training,
        # Keep the established ``metrics`` key for downstream notebooks and
        # add an explicit alias that makes the before/after comparison clear.
        "metrics": metrics_after_training,
        "metrics_after_training": metrics_after_training,
        "training_effect": {
            "relative_l2_error_ratio_after_over_before": (
                metrics_after_training["relative_l2"]
                / metrics_before_training["relative_l2"]
            )
        },
        "artifacts": {"held_out_test_example": test_example},
        "candidate_note": str(cfg.custom.candidate_note),
    }
    _write_metrics(str(cfg.custom.metrics_file), payload)

    print("=" * 72)
    print("별도 테스트 데이터 평가 — 학습 종료 시점 모델")
    print(
        "학습 전 상대 L2 오차: "
        f"{metrics_before_training['relative_l2']:.6e}"
    )
    print(f"학습 후 RMSE:        {metrics_after_training['rmse']:.6e}")
    print(f"학습 후 MAE:         {metrics_after_training['mae']:.6e}")
    print(
        "학습 후 상대 L2 오차: "
        f"{metrics_after_training['relative_l2']:.6e}"
    )
    print(f"학습 파라미터 수: {trainable_parameters:,}")
    if peak_memory_allocated_bytes is not None:
        print(f"최대 PyTorch 메모리: {peak_memory_allocated_bytes / 2**30:.2f} GiB")
    print("=" * 72)


if __name__ == "__main__":
    run()
