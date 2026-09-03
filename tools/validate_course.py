#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Static release checks for the KSC 2026 offline course bundle."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = DEFAULT_ROOT
PARTICIPANT_VALIDATOR = ROOT / "tools/validate_participant_release.py"
STATIC_ONLY = False

BOOST_VERSION = "1.83.0"
BOOST_SOURCE = "https://archives.boost.io/release/1.83.0/source/boost_1_83_0.tar.gz"
BOOST_SHA256 = "c0685b68dd44cc46574cce86c4e17c0f611b15e195be9848dfd0769a0a207628"
BOOST_LICENSE_IN_IMAGE = "/opt/ksc2026/licenses/Boost-LICENSE_1_0.txt"
BOOST_COMPONENT_VALUE = "1.83.0 (statically linked into nvbandwidth)"
BOOST_LINKAGE = "Static library linked into nvbandwidth; Boost is not required as a runtime shared library."
BOOST_SOURCE_ENTRY = {
    "name": "Boost.ProgramOptions",
    "version": BOOST_VERSION,
    "source": BOOST_SOURCE,
    "sha256": BOOST_SHA256,
    "license": "BSL-1.0",
    "linkage": BOOST_LINKAGE,
    "license_in_image": BOOST_LICENSE_IN_IMAGE,
}

REQUIRED_PATHS = (
    ".dockerignore",
    "course-release.json",
    "README.md",
    "PROVENANCE.md",
    "00_Start_Here.ipynb",
    "01_GH200/README.md",
    "01_GH200/01_CPU_Compile_and_Tune.ipynb",
    "01_GH200/02_GPU_Memory_Profile.ipynb",
    "02_PhysicsNeMo/README.md",
    "02_PhysicsNeMo/01_Projectile_PINN.ipynb",
    "02_PhysicsNeMo/02_Poisson_FNO.ipynb",
    "02_PhysicsNeMo/optional/README.md",
    "02_PhysicsNeMo/optional/FNO_Mode_Ablation.ipynb",
    "labs/README.md",
    "labs/gh200/README.md",
    "labs/gh200/blas/Makefile",
    "labs/gh200/blas/dgemm.c",
    "labs/gh200/cuda_memory/explicit.cu",
    "labs/gh200/cuda_memory/managed.cu",
    "labs/gh200/cuda_memory/hmm.cu",
    "labs/projectile/images/projectile.svg",
    "labs/projectile/images/physicsnemo_sym_workflow.webp",
    "labs/poisson_fno/images/fno_data_flow.svg",
    "Dockerfile",
    "Singularity",
    "Deployment_Guide.MD",
    "container/README.md",
    "container/entrypoint.sh",
    "container/smoke_test.sh",
    "container/build_image.sh",
    "container/build_sif.sh",
    "container/Apptainer.kisti.def",
    "container/build_kisti_sif.sh",
    "container/ksc2026-image.json",
    "container/third-party-sources.json",
    "operations/README.md",
    "operations/admin/publish-course.sh",
    "operations/admin/refresh-course",
    "operations/admin/participant/README.md",
    "operations/admin/participant/KSC2026-Shared-Launcher-Deployment-Guide.md",
    "operations/admin/participant/KSC2026-Admin-Deployment-Guide.md",
    "operations/admin/participant/install-participants.sh",
    "operations/admin/participant/tests/run-tests.sh",
    "operations/admin/participant/tests/test-runtime-lock.py",
    "operations/admin/participant/tests/test_trusted_course_validation.py",
    "operations/KSC2026-Pilot-Validation-Guide.md",
    "operations/participant/README.md",
    "operations/participant/site.env.example",
    "operations/participant/ksc2026",
    "operations/participant/start-jupyter",
    "operations/participant/session-controller.py",
    "operations/participant/jupyter-job.sh",
    "operations/participant/tests/run-session-tests.sh",
    "operations/participant/tests/test_session_controller.py",
    "operations/participant/tests/test_runtime_contract.py",
    "operations/participant/tests/test_entrypoint.py",
    "tools/validate_participant_release.py",
)

PARTICIPANT_PATHS = (
    "README.md",
    "00_Start_Here.ipynb",
    "01_GH200",
    "02_PhysicsNeMo",
    "labs",
    "LICENSE",
    "PROVENANCE.md",
    "course-release.json",
)

ACTIVE_NOTEBOOK_PATHS = (
    "00_Start_Here.ipynb",
    "01_GH200/01_CPU_Compile_and_Tune.ipynb",
    "01_GH200/02_GPU_Memory_Profile.ipynb",
    "02_PhysicsNeMo/01_Projectile_PINN.ipynb",
    "02_PhysicsNeMo/02_Poisson_FNO.ipynb",
    "02_PhysicsNeMo/optional/FNO_Mode_Ablation.ipynb",
)
ACTIVE_NOTEBOOKS = tuple(ROOT / path for path in ACTIVE_NOTEBOOK_PATHS)

OLD_PARTICIPANT_PATHS = (
    "02_Poisson_FNO_GH200.ipynb",
    "03_Optional_FNO_Mode_Ablation.ipynb",
    "01_GH200_Compile_Profile_Tune.ipynb",
    "02_PhysicsNeMo_Projectile_PINN.ipynb",
    "03_PhysicsNeMo_Poisson_FNO_GH200.ipynb",
    "03_Optional/",
)

COMMAND_PATTERN = re.compile(
    r"(?im)^\s*(?:!|%|%%bash\s*)?(?:sudo\s+)?(?:"
    r"apt(?:-get)?(?:\s|$)|"
    r"pip3?(?:\s|$)|"
    r"python3?\s+-m\s+pip(?:\s|$)|"
    r"git\s+clone(?:\s|$)|"
    r"wget(?:\s|$)|"
    r"curl(?:\s|$)"
    r")"
)
NETWORK_IMPORT_PATTERN = re.compile(
    r"(?m)^\s*(?:from|import)\s+(?:requests|urllib|socket|gdown)(?:\.|\s|$)"
)
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_LINK_PATTERN = re.compile(r"(?:href|src)=[\"']([^\"']+)[\"']", re.I)
KOREAN_COPY_FORBIDDEN = (
    "한 물리 해에서 함수 간 사상으로",
    "해의 family",
    "u label을 sampling",
    "README와 `02`의 초록색 그림",
)


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.passes: list[str] = []

    def require(self, condition: bool, message: str) -> None:
        if condition:
            self.passes.append(message)
        else:
            self.errors.append(message)

    def finish(self) -> int:
        for message in self.passes:
            print(f"PASS  {message}")
        for message in self.errors:
            print(f"FAIL  {message}")
        print(f"\nsummary: {len(self.passes)} passed, {len(self.errors)} failed")
        return 1 if self.errors else 0


def load_notebook(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_text(cell: dict[str, object]) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def notebook_python_source(cell: dict[str, object]) -> str:
    code = source_text(cell)
    if cell.get("id") == "start-nvidia-smi-code" and code.strip() == "!nvidia-smi":
        return "pass\n"
    return code


def check_required_files(check: Validation) -> None:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).is_file()]
    check.require(not missing, "required course files are present" if not missing else f"missing required files: {missing}")


def check_course_scope(check: Validation) -> None:
    forbidden = [
        path
        for path in ("03_Optional", "optional", "tutorial", "challenge")
        if (ROOT / path).exists()
    ]
    copied_snapshots = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("Original_PhysicsNeMo_Bootcamp")
    ]
    check.require(
        not forbidden and not copied_snapshots,
        "optional content is scoped to its owning module and upstream source trees are not copied"
        if not forbidden and not copied_snapshots
        else f"out-of-scope roots or copied snapshots found: roots={forbidden}, snapshots={copied_snapshots}",
    )


def check_notebooks(check: Validation) -> None:
    ids: set[str] = set()
    for path in ACTIVE_NOTEBOOKS:
        if not path.is_file():
            continue
        try:
            notebook = load_notebook(path)
        except (json.JSONDecodeError, OSError) as error:
            check.errors.append(f"{path.relative_to(ROOT)} is not valid notebook JSON: {error}")
            continue
        for index, cell in enumerate(notebook.get("cells", [])):
            if not isinstance(cell, dict):
                check.errors.append(f"{path.relative_to(ROOT)} cell {index} is not an object")
                continue
            cell_id = str(cell.get("id", ""))
            if not cell_id:
                check.errors.append(f"{path.relative_to(ROOT)} cell {index} has no id")
            elif cell_id in ids:
                check.errors.append(f"duplicate notebook cell id: {cell_id}")
            else:
                ids.add(cell_id)
            if cell.get("cell_type") == "code":
                code_for_compile = notebook_python_source(cell)
                try:
                    compile(code_for_compile, f"{path.name}:cell-{index}", "exec")
                except SyntaxError as error:
                    check.errors.append(f"{path.relative_to(ROOT)} code cell {index}: {error}")
                if cell.get("outputs"):
                    check.errors.append(f"{path.relative_to(ROOT)} code cell {index} retains execution output")
                if cell.get("execution_count") is not None:
                    check.errors.append(f"{path.relative_to(ROOT)} code cell {index} retains execution_count")
    check.require(
        not any("code cell" in item for item in check.errors),
        "notebook Python and the approved nvidia-smi shell cell parse, and outputs are cleared",
    )


def check_start_here_gpu_guidance(check: Validation) -> None:
    path = ROOT / "00_Start_Here.ipynb"
    notebook = load_notebook(path)
    code = "\n".join(
        source_text(cell)
        for cell in notebook.get("cells", [])
        if isinstance(cell, dict) and cell.get("cell_type") == "code"
    )
    markdown = "\n".join(
        source_text(cell)
        for cell in notebook.get("cells", [])
        if isinstance(cell, dict) and cell.get("cell_type") == "markdown"
    )
    required_code = (
        "!nvidia-smi",
        'os.environ.get("KSC_EXPECTED_GPU_COUNT")',
        'os.environ.get("SLURM_GPUS_ON_NODE")',
        "EXPECTED_GPU_COUNT = configured_gpu_count or slurm_gpu_count",
        "GPU_COUNT_READY = visible_gpu_count == EXPECTED_GPU_COUNT",
        "visible_gpu_count in {1, 4}",
        "CUDA_TENSOR_READY = GPU_COUNT_READY",
        "NVIDIA_SMI_COMMAND_READY = query.returncode == 0",
        "len(majors) == visible_gpu_count",
        "and bool(majors)",
        "all(major >= 570 for major in majors)",
        "and NVIDIA_SMI_COMMAND_READY",
    )
    forbidden_code = (
        "MINIMUM_GPU_COUNT",
        "visible_gpu_count >=",
    )
    required_markdown = (
        "Jupyter 코드 셀에서 Linux 명령을 실행할 때는 명령 앞에 `!`",
        "로그인 터미널에서는 느낌표 없이 `nvidia-smi`",
        "참가자 세션에는 GPU 한 개가 배정",
        "강사 세션에는 여러 GPU가 보일 수 있습니다",
        "참가자용 한 개 또는 강사용 네 개",
        "`CUDA Version`",
        "드라이버는 R570 이상",
        "실제 CUDA 텐서 연산까지 통과해야 최종 정상",
    )
    valid = (
        all(marker in code for marker in required_code)
        and not any(marker in code for marker in forbidden_code)
        and all(marker in markdown for marker in required_markdown)
    )
    check.require(
        valid,
        "Start Here validates the launcher/Slurm GPU allocation and explains nvidia-smi/R570 validation",
    )


def iter_runtime_text() -> list[tuple[Path, str]]:
    files: list[Path] = []
    for extension in ("*.py", "*.sh", "*.c", "*.cu", "Makefile"):
        files.extend((ROOT / "labs").rglob(extension))
    for name in ("container/entrypoint.sh", "container/smoke_test.sh"):
        path = ROOT / name
        if path.is_file():
            files.append(path)
    singularity = ROOT / "Singularity"
    if singularity.is_file():
        text = singularity.read_text(encoding="utf-8")
        match = re.search(r"(?ms)^%runscript\s*$\n(.*?)(?=^%\w|\Z)", text)
        if match:
            files.append(singularity)
    kisti_definition = ROOT / "container/Apptainer.kisti.def"
    if kisti_definition.is_file():
        text = kisti_definition.read_text(encoding="utf-8")
        match = re.search(r"(?ms)^%runscript\s*$\n(.*?)(?=^%\w|\Z)", text)
        if match:
            files.append(kisti_definition)
    result: list[tuple[Path, str]] = []
    for path in sorted(set(files)):
        text = path.read_text(encoding="utf-8", errors="replace")
        if path in (singularity, kisti_definition):
            match = re.search(r"(?ms)^%runscript\s*$\n(.*?)(?=^%\w|\Z)", text)
            text = match.group(1) if match else ""
        result.append((path, text))
    for path in ACTIVE_NOTEBOOKS:
        if path.is_file():
            notebook = load_notebook(path)
            code = "\n".join(
                source_text(cell)
                for cell in notebook.get("cells", [])
                if isinstance(cell, dict) and cell.get("cell_type") == "code"
            )
            result.append((path, code))
    return result


def check_offline_runtime(check: Validation) -> None:
    violations: list[str] = []
    for path, text in iter_runtime_text():
        for pattern in (COMMAND_PATTERN, NETWORK_IMPORT_PATTERN):
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{path.relative_to(ROOT)}:{line}: {match.group(0).strip()}")
    check.require(
        not violations,
        "runtime install/download/network calls are 0" if not violations else "runtime network violations: " + "; ".join(violations),
    )


def local_targets(text: str) -> list[str]:
    return MARKDOWN_LINK_PATTERN.findall(text) + HTML_LINK_PATTERN.findall(text)


def resolve_link(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().strip("<>")
    if not target or target.startswith("#"):
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith(("mailto:", "data:")):
        return None
    path = unquote(parsed.path)
    if not path:
        return None
    return (source.parent / path).resolve()


def check_links(check: Validation) -> None:
    documents = sorted(path for path in ROOT.rglob("*.md") if ".git" not in path.parts)
    missing: list[str] = []
    for path in documents:
        if not path.is_file():
            continue
        for target in local_targets(path.read_text(encoding="utf-8")):
            resolved = resolve_link(path, target)
            if resolved is not None and not resolved.exists():
                missing.append(f"{path.relative_to(ROOT)} -> {target}")
    for path in ACTIVE_NOTEBOOKS:
        if not path.is_file():
            continue
        notebook = load_notebook(path)
        markdown = "\n".join(
            source_text(cell)
            for cell in notebook.get("cells", [])
            if isinstance(cell, dict) and cell.get("cell_type") == "markdown"
        )
        for target in local_targets(markdown):
            resolved = resolve_link(path, target)
            if resolved is not None and not resolved.exists():
                missing.append(f"{path.relative_to(ROOT)} -> {target}")
    check.require(not missing, "all local Markdown/notebook links resolve" if not missing else "broken local links: " + "; ".join(missing))


def check_participant_payload_closure(check: Validation) -> None:
    try:
        manifest = json.loads((ROOT / "course-release.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        check.require(False, f"participant payload manifest cannot be read: {error}")
        return

    paths = manifest.get("participant_paths")
    if paths != list(PARTICIPANT_PATHS):
        check.require(False, "participant payload closure requires the approved path list")
        return

    try:
        with tempfile.TemporaryDirectory(prefix="ksc2026-participant-release-") as temporary:
            staging = Path(temporary)
            for relative in paths:
                source = ROOT / relative
                target = staging / relative
                if source.is_symlink():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(os.readlink(source))
                elif source.is_dir():
                    shutil.copytree(source, target, symlinks=True)
                elif source.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                else:
                    raise FileNotFoundError(relative)

            environment = {
                "LC_ALL": "C",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            result = subprocess.run(
                [sys.executable, "-I", "-B", str(PARTICIPANT_VALIDATOR), str(staging)],
                cwd=str(ROOT),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        check.require(False, f"participant payload closure check could not run: {error}")
        return

    passed = (
        result.returncode == 0
        and "KSC2026_PARTICIPANT_RELEASE_VALID=1" in result.stdout
    )
    detail = result.stdout.strip()[-4000:] if not passed else ""
    check.require(
        passed,
        "participant release passes the canonical payload validator"
        if passed
        else f"participant release validation failed with rc={result.returncode}: {detail}",
    )


def check_python(check: Validation) -> None:
    bad: list[str] = []
    python_sources = sorted((ROOT / "labs").rglob("*.py"))
    python_sources.extend(sorted((ROOT / "operations").rglob("*.py")))
    for path in python_sources + [Path(__file__)]:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            bad.append(f"{path.relative_to(ROOT)}: {error}")
    check.require(not bad, "Python sources parse" if not bad else "Python syntax errors: " + "; ".join(bad))


def check_login_node_validator_python36(check: Validation) -> None:
    path = ROOT / "tools/validate_participant_release.py"
    text = path.read_text(encoding="utf-8")
    try:
        ast.parse(text, filename=str(path), feature_version=(3, 6))
    except SyntaxError as error:
        check.require(False, f"participant validator must parse on KISTI login-node Python 3.6: {error}")
        return
    forbidden = ("from __future__ import annotations", "list[", "tuple[", "dict[", "set[", " | None")
    compatible = not any(marker in text for marker in forbidden)
    check.require(
        compatible,
        "participant validator is compatible with KISTI login-node Python 3.6 syntax"
        if compatible
        else "participant validator contains typing syntax newer than KISTI login-node Python 3.6",
    )


def check_login_node_participant_python36(check: Validation) -> None:
    """Mirror the login-node syntax check before a live workspace refresh."""

    bad: list[str] = []
    for path in sorted((ROOT / "labs").rglob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 6))
        except SyntaxError as error:
            bad.append(f"{path.relative_to(ROOT)}: {error}")
    for path in ACTIVE_NOTEBOOKS:
        if not path.is_file():
            continue
        notebook = load_notebook(path)
        for index, cell in enumerate(notebook.get("cells", [])):
            if not isinstance(cell, dict) or cell.get("cell_type") != "code":
                continue
            try:
                ast.parse(
                    notebook_python_source(cell),
                    filename=f"{path}:cell-{index}",
                    feature_version=(3, 6),
                )
            except SyntaxError as error:
                bad.append(f"{path.relative_to(ROOT)} cell {index}: {error}")
    check.require(
        not bad,
        "participant Python sources parse on KISTI login-node Python 3.6"
        if not bad
        else "participant Python 3.6 syntax errors: " + "; ".join(bad),
    )


def check_korean_copy(check: Validation) -> None:
    documents = [
        ROOT / "README.md",
        ROOT / "01_GH200/README.md",
        ROOT / "02_PhysicsNeMo/README.md",
        ROOT / "02_PhysicsNeMo/optional/README.md",
    ]
    text_by_path: list[tuple[Path, str]] = [
        (path, path.read_text(encoding="utf-8"))
        for path in documents
        if path.is_file()
    ]
    for path in ACTIVE_NOTEBOOKS:
        if not path.is_file():
            continue
        notebook = load_notebook(path)
        markdown = "\n".join(
            source_text(cell)
            for cell in notebook.get("cells", [])
            if isinstance(cell, dict) and cell.get("cell_type") == "markdown"
        )
        text_by_path.append((path, markdown))

    violations: list[str] = []
    for path, text in text_by_path:
        for phrase in KOREAN_COPY_FORBIDDEN:
            if phrase in text:
                violations.append(f"{path.relative_to(ROOT)}: {phrase}")
        if re.search(r'(?m)^\s*"\s*$', text):
            violations.append(f"{path.relative_to(ROOT)}: generated quote artifact in Markdown")
    check.require(
        not violations,
        "known literal-translation and generated-Markdown defects are absent"
        if not violations
        else "Korean copy defects: " + "; ".join(violations),
    )


def check_operations(check: Validation) -> None:
    operations = ROOT / "operations"
    if not operations.is_dir():
        check.errors.append("operations package is missing")
        return
    operation_files = [path for path in operations.rglob("*") if path.is_file()]
    runtime_texts = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in operation_files
        if "tests" not in path.relative_to(operations).parts
        and (
            path.suffix.lower() in {".sh", ".py", ".command", ".ps1", ".cmd"}
            or path.name in {"ksc2026", "start-jupyter", "jupyter-job.sh"}
        )
    )
    forbidden = [marker for marker in ("sshpass", "Password(otp)", "CUDA_VISIBLE_DEVICES=") if marker in runtime_texts]
    check.require(
        not forbidden,
        "shared runtime contains no password automation or static GPU override"
        if not forbidden
        else f"forbidden shared-runtime automation markers: {forbidden}",
    )
    publisher_path = operations / "admin/publish-course.sh"
    publisher = publisher_path.read_text(encoding="utf-8") if publisher_path.is_file() else ""
    publisher_required = (
        "canonical_parent=/scratch/hackathon",
        "canonical_root=/scratch/hackathon/ksc2026",
        '"0:0:1777"',
        '"$actor_uid:755"',
        '"$actor_uid" != 0',
        "--frozen-commit",
        "allowed_site_keys=",
        'deployment_lock="${admin_root}/deployment.lock"',
        '"$actor_uid:644:1"',
        "( umask 022; set -o noclobber;",
        "flock -x -n 9",
        "canonical_repo_url=https://github.com/yang926/KSC2026-GH200-PhysicsNeMo-Tutorial.git",
        'trusted_tools_dir="${admin_root}/libexec"',
        'stat -Lc \'%d:%i\' /dev/fd/9',
        "git_safe --git-dir=\"$mirror_dir\" ls-tree -rlz --full-tree",
        "max_course_entries=10000",
        "max_course_blob_bytes=$((256 * 1024 * 1024))",
        "max_course_total_bytes=$((2 * 1024 * 1024 * 1024))",
        "merge-base --is-ancestor \"$active_commit\" \"$course_commit\"",
        "site.env에는 KSC_COURSE_RELEASE 항목이 정확히 하나 있어야 합니다",
        "새 강의 release를 중앙 설정에 활성화하지 못했습니다",
        '--root "$validation_dir"',
        '--participant-validator "$trusted_participant_validator"',
        "--static-only",
        '"$runtime_python" -I -B "$trusted_participant_validator" "$staging_dir"',
    )
    publisher_defects = [marker for marker in publisher_required if marker not in publisher]
    if 'source "$site_env"' in publisher:
        publisher_defects.append("runtime site.env is shell-sourced")
    if "KSC_COURSE_FROZEN_COMMIT" in publisher:
        publisher_defects.append("freeze state is read from runtime site.env")
    for forbidden_execution in (
        "python3 tools/validate_course.py",
        '"${validation_dir}/tools/validate_participant_release.py"',
    ):
        if forbidden_execution in publisher:
            publisher_defects.append(
                f"fetched Git validator is executed: {forbidden_execution}"
            )
    check.require(
        not publisher_defects,
        "course publisher enforces the rootless central-owner path, data-only site config, CLI freeze, and shared deployment lock"
        if not publisher_defects
        else f"course publisher safety defects: {publisher_defects}",
    )
    participant_wrapper_path = operations / "participant/ksc2026"
    participant_wrapper = (
        participant_wrapper_path.read_text(encoding="utf-8")
        if participant_wrapper_path.is_file()
        else ""
    )
    participant_installer_path = operations / "admin/participant/install-participants.sh"
    participant_installer = (
        participant_installer_path.read_text(encoding="utf-8")
        if participant_installer_path.is_file()
        else ""
    )
    atomic_runtime_required = {
        "participant wrapper": (
            'exec 9<"$deployment_lock"',
            "flock -s 9",
            "stat -Lc '%d:%i' /dev/fd/9",
            '"$central_uid:644:1"',
            "without close-on-exec",
        ),
        "participant installer": (
            'deployment_lock="$admin_root/deployment.lock"',
            '"$central_uid:644:1"',
            "flock -x -n 9",
            "CENTRAL_ENTRYPOINT_IMMUTABLE_CONTENT_MISMATCH",
            'if (( admin_tools_only == 0 )) && [[ "$entrypoint_action" == INSTALL ]]',
            '"$central_root/admin/libexec/validate_course.py"',
            '"$central_root/admin/libexec/validate_participant_release.py"',
            '"$central_root/admin/libexec/publish-course.sh"',
            '"$central_root/admin/bin/refresh-course"',
            "declare -a target_modes=(0755 0644 0755 0644 0600 0600 0700 0700)",
            "SITE_ENV_COURSE_RELEASE_WOULD_ROLL_BACK",
        ),
    }
    atomic_runtime_text = {
        "participant wrapper": participant_wrapper,
        "participant installer": participant_installer,
    }
    atomic_runtime_defects = [
        f"{label}: {marker}"
        for label, markers in atomic_runtime_required.items()
        for marker in markers
        if marker not in atomic_runtime_text[label]
    ]
    participant_lock_test = operations / "admin/participant/tests/test-runtime-lock.py"
    if not participant_lock_test.is_file() or not os.access(participant_lock_test, os.X_OK):
        atomic_runtime_defects.append("executable runtime-lock test is missing")
    trusted_validation_test = operations / "admin/participant/tests/test_trusted_course_validation.py"
    if not trusted_validation_test.is_file() or not os.access(trusted_validation_test, os.X_OK):
        atomic_runtime_defects.append("executable trusted-validation test is missing")
    refresh_path = operations / "admin/refresh-course"
    refresh = refresh_path.read_text(encoding="utf-8") if refresh_path.is_file() else ""
    for marker in (
        "/scratch/hackathon/ksc2026/admin/bin/refresh-course",
        'publisher="$central_root/admin/libexec/publish-course.sh"',
        "KSC_REFRESH_ERROR=NO_OPTIONS_ALLOWED",
    ):
        if marker not in refresh:
            atomic_runtime_defects.append(f"owner refresh command: {marker}")
    check.require(
        not atomic_runtime_defects,
        "participant runtime holds a shared deployment lock across exec and keeps its stable entrypoint immutable"
        if not atomic_runtime_defects
        else f"participant atomic-runtime defects: {atomic_runtime_defects}",
    )
    active_participant_docs = (
        ROOT / "README.md",
        ROOT / "00_Start_Here.ipynb",
        ROOT / "Deployment_Guide.MD",
        operations / "KSC2026-Pilot-Validation-Guide.md",
        operations / "admin/participant/README.md",
        operations / "admin/participant/KSC2026-Shared-Launcher-Deployment-Guide.md",
        operations / "admin/participant/KSC2026-Admin-Deployment-Guide.md",
        operations / "participant/README.md",
        operations / "participant/site.env.example",
    )
    obsolete_participant_markers = (
        "/scratch/ksc2026-shared",
        "/shared/ksc2026",
        "/scratch/$USER/ksc2026/bin/ksc2026",
        "/scratch/<교육계정>/ksc2026/bin/ksc2026",
        "KSC2026-Participant-Launcher-Install-Guide.md",
        "--pilot-account",
        "PARTICIPANT_WRAPPER",
        "account-map",
        "account_map",
        "instructor-route",
        "KSC_INSTRUCTOR",
        "KSC_STUDENT_RESERVATION",
        "--status",
        "--preflight",
        "--fresh-course",
        "--refresh-course",
        "계정→계산 노드",
        "참가자별 전용 노드",
    )
    obsolete_locations: list[str] = []
    for path in active_participant_docs:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in obsolete_participant_markers:
            if marker in text:
                obsolete_locations.append(f"{path.relative_to(ROOT)}: {marker}")
    check.require(
        not obsolete_locations,
        "active participant docs use only the canonical shared launcher path"
        if not obsolete_locations
        else "obsolete participant deployment references: " + "; ".join(obsolete_locations),
    )
    public_contract_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in active_participant_docs
        if path.is_file()
    )
    public_identity_defects = []
    literal_ips = set(
        re.findall(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])", public_contract_text)
    )
    site_ips = sorted(literal_ips.difference({"0.0.0.0", "127.0.0.1"}))
    if site_ips:
        public_identity_defects.append("literal site IPv4 address")
    if re.search(r"(?<![A-Za-z0-9])ki[0-9]{5}(?![A-Za-z0-9])", public_contract_text):
        public_identity_defects.append("literal KISTI account id")
    check.require(
        not public_identity_defects,
        "public participant docs contain no literal site IP or account id"
        if not public_identity_defects
        else f"public participant identity defects: {public_identity_defects}",
    )
    topology_paths = (
        ROOT / "Deployment_Guide.MD",
        ROOT / "container/README.md",
        operations / "participant/session-controller.py",
        operations / "participant/tests/test_entrypoint.py",
        operations / "participant/tests/test_session_controller.py",
    )
    topology_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in topology_paths
        if path.is_file()
    )
    topology_defects = []
    if re.search(r"\bgpu-login[0-9]+\b", topology_text):
        topology_defects.append("literal KISTI login-node name")
    if re.search(r"\bgpu[0-9]{4}\b", topology_text):
        topology_defects.append("literal KISTI compute-node name")
    check.require(
        not topology_defects,
        "public release contains no literal KISTI login or compute node names"
        if not topology_defects
        else f"public topology defects: {topology_defects}",
    )
    controller = (operations / "participant/session-controller.py").read_text(encoding="utf-8")
    payload = (operations / "participant/jupyter-job.sh").read_text(encoding="utf-8")
    shared_runtime = "\n".join((
        (operations / "participant/ksc2026").read_text(encoding="utf-8"),
        (operations / "participant/start-jupyter").read_text(encoding="utf-8"),
        controller,
        payload,
    ))
    scheduler_required = (
        'f"--partition={partition}"',
        '"--nodes=1"',
        '"--ntasks=1"',
        'f"--gres=gpu:{gres}:1"',
        '"--time=1-00:00:00"',
        'compute_node="$(hostname -s)"',
        'remote_port=$((18880 + 10#$slurm_job_gpus))',
        'c.ServerApp.ip = \'0.0.0.0\'',
        'LOCAL_JUPYTER_PORT = 8888',
        'KSC_LOGIN_HOST',
    )
    scheduler_missing = [marker for marker in scheduler_required if marker not in shared_runtime]
    forbidden_dynamic = [
        marker
        for marker in ("--nodelist", "--exclude", "--exclusive", "KSC_EXPECTED_NODE", "KSC_REMOTE_PORT", "CUDA_VISIBLE_DEVICES=")
        if marker in shared_runtime
    ]
    check.require(
        not scheduler_missing and not forbidden_dynamic,
        "shared launcher requests one dynamic GH200 and derives the tunnel endpoint from Slurm"
        if not scheduler_missing and not forbidden_dynamic
        else f"shared dynamic-launcher defects: missing={scheduler_missing}, forbidden={forbidden_dynamic}",
    )


def check_identity_and_pins(check: Validation) -> None:
    text_files = [ROOT / "README.md", ROOT / "PROVENANCE.md", ROOT / "Dockerfile", ROOT / "Singularity", ROOT / "container/Apptainer.kisti.def", ROOT / "Deployment_Guide.MD"]
    combined = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in text_files if path.is_file())
    old = [marker for marker in OLD_PARTICIPANT_PATHS if marker in combined]
    check.require(not old, "old participant paths are absent from active docs/recipes" if not old else f"old paths found: {old}")

    dockerfile = ROOT / "Dockerfile"
    docker = dockerfile.read_text(encoding="utf-8") if dockerfile.is_file() else ""
    check.require("linux/arm64" in docker and "sha256:4e7f82e33d886828efd1e4d65236f5e44c96dfbd3d316c58723eff9b9298eda6" in docker, "Docker final image is pinned to PhysicsNeMo 25.11 ARM64 digest")
    check.require("sha256:d5b8001ed137d70417454279c46f6dde335337efbbd6742a4b1c103cbf85831b" in docker, "NVHPC 25.5 ARM64 stage is digest-pinned")
    check.require(BOOST_SHA256 in docker, "Boost.ProgramOptions 1.83.0 archive checksum is pinned")
    check.require("6dd2a63ac9d32643b7cc636eab57bf4e57d0ed1fff926dfbc5d3d97f2d2be3a6" in docker, "OpenBLAS 0.3.31 archive checksum is pinned")
    check.require("b3622945eb7fce2b4e1aea7d13de04f415f4d998db602893201a904320cf2d39" in docker, "nvbandwidth 0.8 archive checksum is pinned")
    check.require(
        not re.search(r"\bapt(?:-get)?\b", docker),
        "Docker recipe contains no apt or apt-get dependency path",
    )
    check.require(
        'ENTRYPOINT ["/opt/nvidia/physicsnemo_env.sh", "/opt/ksc2026/container/entrypoint.sh"]' in docker,
        "Docker runtime preserves the official PhysicsNeMo environment entrypoint",
    )
    cuda_path_prefix = "/opt/ksc2026/bin:/usr/local/cuda/bin:/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/compilers/bin"
    check.require(
        cuda_path_prefix in docker,
        "PhysicsNeMo CUDA 13.0 tools take precedence over the CUDA copy bundled with NVHPC",
    )
    nvpl_root = "/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/math_libs/nvpl"
    nvpl_lib = f"{nvpl_root}/lib"
    cuda12_math_lib = "/opt/nvidia/hpc_sdk/Linux_aarch64/25.5/math_libs/lib64"
    check.require(
        f'NVPL_ROOT="{nvpl_root}"' in docker
        and f'LD_LIBRARY_PATH="${{LD_LIBRARY_PATH}}:{nvpl_lib}:' in docker
        and cuda12_math_lib not in docker,
        "Docker exposes the real NVPL root after the PhysicsNeMo CUDA runtime and excludes NVHPC CUDA 12.9 math libraries",
    )

    nvpl_validation_files = (
        ROOT / "Dockerfile",
        ROOT / "container/Apptainer.kisti.def",
        ROOT / "container/smoke_test.sh",
    )
    nvpl_filename_assumptions = [
        str(path.relative_to(ROOT))
        for path in nvpl_validation_files
        if path.is_file() and "libnvpl_blas" in path.read_text(encoding="utf-8", errors="replace")
    ]
    check.require(
        not nvpl_filename_assumptions,
        "NVPL validation uses the bundled root plus an actual DGEMM compile/link/run, without assuming a library filename"
        if not nvpl_filename_assumptions
        else f"NVPL library filename assumptions remain: {nvpl_filename_assumptions}",
    )

    singularity = (ROOT / "Singularity").read_text(encoding="utf-8") if (ROOT / "Singularity").is_file() else ""
    check.require("docker-archive" in singularity and "%post" not in singularity, "SIF consumes the canonical Docker artifact without a second install step")
    check.require(
        cuda_path_prefix in singularity,
        "Docker-to-SIF conversion preserves the PhysicsNeMo CUDA tool precedence",
    )
    check.require(
        f"export NVPL_ROOT={nvpl_root}" in singularity
        and f"export LD_LIBRARY_PATH=${{LD_LIBRARY_PATH}}:{nvpl_lib}:" in singularity
        and cuda12_math_lib not in singularity,
        "Docker-to-SIF conversion preserves the real NVPL root without overriding PhysicsNeMo CUDA",
    )
    check.require(
        "exec /opt/nvidia/physicsnemo_env.sh /opt/ksc2026/container/entrypoint.sh" in singularity,
        "SIF runscript preserves the official PhysicsNeMo environment entrypoint",
    )

    kisti_definition_path = ROOT / "container/Apptainer.kisti.def"
    kisti_definition = kisti_definition_path.read_text(encoding="utf-8") if kisti_definition_path.is_file() else ""
    kisti_required = (
        "Stage: nvhpc",
        "Stage: final",
        "%files from nvhpc",
        "/opt/nvidia/hpc_sdk /opt/nvidia/hpc_sdk",
        "sha256:4e7f82e33d886828efd1e4d65236f5e44c96dfbd3d316c58723eff9b9298eda6",
        "sha256:d5b8001ed137d70417454279c46f6dde335337efbbd6742a4b1c103cbf85831b",
        "6dd2a63ac9d32643b7cc636eab57bf4e57d0ed1fff926dfbc5d3d97f2d2be3a6",
        "b3622945eb7fce2b4e1aea7d13de04f415f4d998db602893201a904320cf2d39",
        "%test",
        "/opt/ksc2026/container/smoke_test.sh --static",
        "exec /opt/nvidia/physicsnemo_env.sh /opt/ksc2026/container/entrypoint.sh",
        ".dockerignore /opt/ksc2026/course-source/.dockerignore",
    )
    kisti_missing = [marker for marker in kisti_required if marker not in kisti_definition]
    check.require(
        not kisti_missing,
        "KISTI direct Apptainer recipe pins both ARM64 stages and preserves the runtime/test contract"
        if not kisti_missing
        else f"KISTI direct Apptainer recipe markers missing: {kisti_missing}",
    )
    check.require(
        cuda_path_prefix in kisti_definition,
        "KISTI SIF preserves the PhysicsNeMo CUDA tool precedence alongside NVHPC",
    )
    check.require(
        f"export NVPL_ROOT={nvpl_root}" in kisti_definition
        and f"export LD_LIBRARY_PATH=${{LD_LIBRARY_PATH:-}}:{nvpl_lib}:" in kisti_definition
        and cuda12_math_lib not in kisti_definition,
        "KISTI SIF exposes the real NVPL root after PhysicsNeMo CUDA and excludes NVHPC CUDA 12.9 math libraries",
    )

    smoke_test_path = ROOT / "container/smoke_test.sh"
    smoke_test = smoke_test_path.read_text(encoding="utf-8") if smoke_test_path.is_file() else ""
    check.require(
        "math_libs/nvpl" in smoke_test
        and "math_libs/lib64 must not override the PhysicsNeMo CUDA runtime" in smoke_test,
        "container smoke test rejects the known CUDA 12.9 runtime override regression",
    )

    post_match = re.search(r"(?ms)^%post\s*$\n(.*?)(?=^%[A-Za-z]|\Z)", kisti_definition)
    kisti_post = post_match.group(1) if post_match else ""
    check.require(bool(post_match), "KISTI direct Apptainer recipe has a %post section")
    apt_pattern = re.compile(
        r"(?m)(?:^[ \t]*|(?:&&|\|\||;|\|)[ \t]*)"
        r"(?:env(?:[ \t]+[A-Za-z_][A-Za-z0-9_]*=[^ \t;|&]+)*[ \t]+)?"
        r"(?:sudo[ \t]+)?apt(?:-get)?(?=[ \t\\;|&()<>]|$)"
    )
    apt_invocations = [
        kisti_post.count("\n", 0, match.start()) + 1
        for match in apt_pattern.finditer(kisti_post)
    ]
    check.require(
        not apt_invocations,
        "KISTI %post contains no executable apt or apt-get commands"
        if not apt_invocations
        else f"KISTI %post executes apt or apt-get on relative lines: {apt_invocations}",
    )

    boost_recipe_required = (
        BOOST_SOURCE,
        BOOST_SHA256,
        "LICENSE_1_0.txt",
        BOOST_LICENSE_IN_IMAGE,
        "--with-libraries=program_options",
        "--with-program_options",
        "link=static",
        "libboost_program_options.a",
        "-DBOOST_ROOT=",
        "-DBOOST_LIBRARYDIR=",
        "-DBoost_NO_SYSTEM_PATHS=ON",
        "-DBoost_NO_BOOST_CMAKE=ON",
        "-DBoost_USE_STATIC_LIBS=ON",
        "-DBoost_USE_STATIC_RUNTIME=OFF",
        "CMakeFiles/nvbandwidth.dir/link.txt",
        "grep --fixed-strings --quiet",
        "readelf -d",
    )
    boost_recipe_missing = [marker for marker in boost_recipe_required if marker not in kisti_post]
    check.require(
        not boost_recipe_missing,
        "KISTI %post pins Boost.ProgramOptions and verifies its static link"
        if not boost_recipe_missing
        else f"KISTI Boost source-build or static-link markers missing: {boost_recipe_missing}",
    )
    check.require(
        not re.search(r"(?m)^\s+(?:assets|labs|operations|01_GH200|02_PhysicsNeMo)/\s", kisti_definition),
        "KISTI direct Apptainer recipe copies course and operations content through an explicit file allow-list",
    )
    host_sources: list[str] = []
    host_destinations: list[str] = []
    malformed_files_lines: list[str] = []
    inside_host_files = False
    for raw_line in kisti_definition.splitlines():
        stripped = raw_line.strip()
        if stripped == "%files":
            inside_host_files = True
            continue
        if inside_host_files and stripped.startswith("%"):
            break
        if not inside_host_files or not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) != 2:
            malformed_files_lines.append(stripped)
            continue
        host_sources.append(fields[0])
        host_destinations.append(fields[1])

    unsafe_sources: list[str] = []
    for source in host_sources:
        source_path = Path(source)
        lower_parts = {part.lower() for part in source_path.parts}
        lower_name = source_path.name.lower()
        if (
            source_path.is_absolute()
            or ".." in source_path.parts
            or source_path.is_symlink()
            or not (ROOT / source_path).is_file()
            or lower_parts.intersection({".git", ".ipynb_checkpoints", "__pycache__", "outputs", "datasets", "participant-bundles"})
            or lower_name in {"site.env", "account-map.csv", "known_hosts"}
            or lower_name.endswith((".pyc", ".sif", ".tar", ".zip"))
            or any(marker in lower_name for marker in ("secret", "credential", "private"))
        ):
            unsafe_sources.append(source)
    duplicate_destinations = sorted(
        destination for destination in set(host_destinations) if host_destinations.count(destination) > 1
    )
    check.require(
        bool(host_sources) and not malformed_files_lines and not unsafe_sources and not duplicate_destinations,
        "every KISTI host allow-list entry is an existing explicit file with a unique image destination"
        if host_sources and not malformed_files_lines and not unsafe_sources and not duplicate_destinations
        else (
            "invalid KISTI host allow-list: "
            f"malformed={malformed_files_lines}, unsafe={unsafe_sources}, duplicate_destinations={duplicate_destinations}"
        ),
    )

    kisti_builder_path = ROOT / "container/build_kisti_sif.sh"
    kisti_builder = kisti_builder_path.read_text(encoding="utf-8") if kisti_builder_path.is_file() else ""
    kisti_builder_required = (
        "aarch64|arm64",
        "module load apptainer/1.4.5",
        "APPTAINER_CACHEDIR",
        "APPTAINER_TMPDIR",
        "build_jobs <= 12",
        "--arch arm64",
        "--mksquashfs-args",
        "/opt/ksc2026/course-source/tools/validate_course.py",
        "smoke_test.sh --gpu",
        "sha256sum --check --strict",
    )
    builder_missing = [marker for marker in kisti_builder_required if marker not in kisti_builder]
    check.require(
        not builder_missing,
        "KISTI SIF builder enforces ARM64, scratch paths, bounded parallelism, checksums, and GPU handoff"
        if not builder_missing
        else f"KISTI SIF builder markers missing: {builder_missing}",
    )
    check.require(
        bool(kisti_builder_path.stat().st_mode & 0o111) if kisti_builder_path.is_file() else False,
        "KISTI SIF builder is executable",
    )

    third_party_path = ROOT / "container/third-party-sources.json"
    if third_party_path.is_file():
        try:
            third_party = json.loads(third_party_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            check.errors.append(f"container/third-party-sources.json is invalid: {error}")
        else:
            sources = third_party.get("sources")
            if not isinstance(sources, list):
                check.errors.append("container/third-party-sources.json sources must be a list")
            else:
                boost_entries = [
                    entry
                    for entry in sources
                    if isinstance(entry, dict) and entry.get("name") == BOOST_SOURCE_ENTRY["name"]
                ]
                check.require(
                    boost_entries == [BOOST_SOURCE_ENTRY],
                    "third-party source manifest records the exact pinned Boost.ProgramOptions source and license"
                    if boost_entries == [BOOST_SOURCE_ENTRY]
                    else f"unexpected Boost.ProgramOptions source entries: {boost_entries}",
                )

    manifest_path = ROOT / "container/ksc2026-image.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            check.errors.append(f"container/ksc2026-image.json is invalid: {error}")
        else:
            serialized = json.dumps(manifest, sort_keys=True)
            required_values = ("linux/arm64", "25.11", "25.5", "0.3.31", "0.8")
            absent = [value for value in required_values if value not in serialized]
            check.require(not absent, "image manifest records required architecture and versions" if not absent else f"manifest values missing: {absent}")
            components = manifest.get("components")
            boost_component = components.get("boost_program_options") if isinstance(components, dict) else None
            check.require(
                boost_component == BOOST_COMPONENT_VALUE,
                "image manifest records Boost.ProgramOptions as statically linked into nvbandwidth"
                if boost_component == BOOST_COMPONENT_VALUE
                else f"image manifest Boost.ProgramOptions value is incorrect: {boost_component!r}",
            )


def check_course_release_manifest(check: Validation) -> None:
    release_path = ROOT / "course-release.json"
    image_path = ROOT / "container/ksc2026-image.json"
    try:
        release = json.loads(release_path.read_text(encoding="utf-8"))
        image = json.loads(image_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        check.errors.append(f"course release metadata is invalid: {error}")
        return

    compatibility = release.get("runtime_compatibility")
    check.require(
        compatibility == image.get("runtime_compatibility")
        and compatibility == "ksc2026-gh200-physicsnemo-25.11-arm64-v1",
        "course release and image manifest use the same runtime compatibility id",
    )
    check.require(
        release.get("repository") == "https://github.com/yang926/KSC2026-GH200-PhysicsNeMo-Tutorial"
        and release.get("participant_entry") == "00_Start_Here.ipynb",
        "course release records the public source repository and participant entry notebook",
    )

    expected_participant_paths = list(PARTICIPANT_PATHS)
    check.require(
        release.get("schema_version") == 2
        and release.get("participant_paths") == expected_participant_paths,
        "course release exposes only the curated participant payload",
    )
    expected_sif = "ee43b2c0735b26a7168e53c7e598dd5dc527b1e23284682f790430656d8bdacf"
    check.require(
        release.get("compatible_sif_sha256") == [expected_sif],
        "course release is bound to the verified KISTI SIF SHA256",
    )
    required = release.get("required_runtime", {})
    component_keys = {
        "physicsnemo", "nvhpc", "nvpl", "openblas", "nvbandwidth",
        "boost_program_options", "cuda_compiler", "nsight_systems",
    }
    expected_capabilities = {
        "arm64",
        "gh200-sm90",
        "cuda-13-forward-compat-r570-or-newer",
        "ssh-tunneled-jupyter",
        "offline-runtime",
    }
    check.require(
        isinstance(required, dict)
        and set(required) == {"image", "platform", "components", "commands", "python_imports", "capabilities"}
        and set(required.get("components", {})) == component_keys
        and required.get("platform") == "linux/arm64"
        and set(required.get("capabilities", [])) == expected_capabilities,
        "course release records the complete typed runtime contract",
    )


def check_spdx(check: Validation) -> None:
    source_files = [
        ROOT / "labs/gh200/notebook_utils.py",
        ROOT / "labs/gh200/blas/Makefile",
        ROOT / "labs/gh200/blas/dgemm.c",
        ROOT / "labs/gh200/cuda_memory/explicit.cu",
        ROOT / "labs/gh200/cuda_memory/managed.cu",
        ROOT / "labs/gh200/cuda_memory/hmm.cu",
    ]
    missing = [str(path.relative_to(ROOT)) for path in source_files if path.is_file() and "SPDX-License-Identifier: Apache-2.0" not in path.read_text(encoding="utf-8")]
    check.require(not missing, "independently authored GH200 sources carry SPDX identifiers" if not missing else f"missing SPDX identifiers: {missing}")


def check_cuda13_prefetch(check: Validation) -> None:
    managed_path = ROOT / "labs/gh200/cuda_memory/managed.cu"
    managed = managed_path.read_text(encoding="utf-8") if managed_path.is_file() else ""
    required_markers = (
        "cudaMemLocation gpu_location{}",
        "gpu_location.type = cudaMemLocationTypeDevice",
        "gpu_location.id = device",
        "cudaMemPrefetchAsync(x, bytes, gpu_location, 0, 0)",
        "cudaMemPrefetchAsync(y, bytes, gpu_location, 0, 0)",
    )
    missing = [marker for marker in required_markers if marker not in managed]
    legacy_calls = re.findall(r"cudaMemPrefetchAsync\([^\n]+,\s*device\s*\)", managed)
    check.require(
        not missing and not legacy_calls,
        "managed-memory lab uses the CUDA 13 cudaMemLocation prefetch API"
        if not missing and not legacy_calls
        else f"CUDA 13 managed-memory prefetch markers missing or legacy calls remain: missing={missing}, legacy={legacy_calls}",
    )


def check_docker_context(check: Validation) -> None:
    ignore_path = ROOT / ".dockerignore"
    if not ignore_path.is_file():
        check.errors.append(".dockerignore is missing")
        return
    rules = [
        line.strip()
        for line in ignore_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    required_rules = {
        "*",
        "!.dockerignore",
        "!Dockerfile",
        "!Singularity",
        "!01_GH200/**",
        "!02_PhysicsNeMo/**",
        "!labs/**",
        "!container/**",
        "!operations/**",
        "**/*secret*",
        "**/*credential*",
        "**/*private*",
    }
    missing = sorted(required_rules.difference(rules))
    deny_first = bool(rules and rules[0] == "*")
    check.require(
        deny_first and not missing,
        "Docker build context is deny-by-default with course allow-lists"
        if deny_first and not missing
        else f"Docker context guard is incomplete: deny_first={deny_first}, missing={missing}",
    )


def check_github_operations_suites(check: Validation) -> None:
    """Run the two local operations suites once when CI invokes this validator."""

    if STATIC_ONLY or os.environ.get("GITHUB_ACTIONS") != "true":
        return
    suites = (
        (
            "unified Jupyter runtime suite",
            ["bash", str(ROOT / "operations/participant/tests/run-session-tests.sh")],
            "UNIFIED_RUNTIME_TESTS=PASS",
        ),
        (
            "central shared-launcher administration suite",
            ["bash", str(ROOT / "operations/admin/participant/tests/run-tests.sh")],
            "UNIFIED_ADMIN_INSTALLER_TESTS=PASS",
        ),
    )
    for label, command, marker in suites:
        try:
            result = subprocess.run(
                command,
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            output = error.stdout or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            check.require(False, f"GitHub {label} timed out: " + output[-4000:])
            continue

        passed = result.returncode == 0 and marker in result.stdout
        check.require(
            passed,
            f"GitHub Actions runs the {label}"
            if passed
            else f"GitHub {label} failed with rc={result.returncode}: {result.stdout[-4000:]}",
        )


def parse_arguments(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="KSC 2026 course bundle static validation"
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help="course checkout/archive root to inspect",
    )
    parser.add_argument(
        "--participant-validator",
        help="trusted validate_participant_release.py path",
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="never execute operation test suites from the inspected root",
    )
    return parser.parse_args(argv)


def configure_paths(arguments: argparse.Namespace) -> None:
    global ROOT, PARTICIPANT_VALIDATOR, STATIC_ONLY, ACTIVE_NOTEBOOKS

    requested_root = Path(arguments.root)
    if not requested_root.is_dir() or requested_root.is_symlink():
        raise SystemExit(f"검증 대상이 안전한 폴더가 아닙니다: {requested_root}")
    ROOT = requested_root.resolve()
    ACTIVE_NOTEBOOKS = tuple(ROOT / path for path in ACTIVE_NOTEBOOK_PATHS)

    requested_validator = Path(
        arguments.participant_validator
        if arguments.participant_validator
        else ROOT / "tools/validate_participant_release.py"
    )
    if not requested_validator.is_file() or requested_validator.is_symlink():
        raise SystemExit(
            f"참가자 검증기가 안전한 regular file이 아닙니다: {requested_validator}"
        )
    PARTICIPANT_VALIDATOR = requested_validator.resolve()
    STATIC_ONLY = bool(arguments.static_only)


def main(argv=None) -> int:
    configure_paths(parse_arguments(argv))
    check = Validation()
    check_required_files(check)
    check_course_scope(check)
    check_notebooks(check)
    check_start_here_gpu_guidance(check)
    check_python(check)
    check_login_node_validator_python36(check)
    check_login_node_participant_python36(check)
    check_korean_copy(check)
    check_offline_runtime(check)
    check_links(check)
    check_operations(check)
    check_identity_and_pins(check)
    check_course_release_manifest(check)
    check_participant_payload_closure(check)
    check_spdx(check)
    check_cuda13_prefetch(check)
    check_docker_context(check)
    check_github_operations_suites(check)
    return check.finish()


if __name__ == "__main__":
    sys.exit(main())
