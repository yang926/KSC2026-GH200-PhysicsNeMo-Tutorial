#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate exactly what a KSC2026 participant receives.

This checker intentionally uses only Python's standard library so it can run on
an internet-isolated KISTI login node before a release is activated.
"""

import ast
import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlsplit

EXPECTED_CAPABILITIES = {
    "arm64",
    "gh200-sm90",
    "cuda-13-forward-compat-r570-or-newer",
    "ssh-tunneled-jupyter",
    "offline-runtime",
}
EXPECTED_PATHS = [
    "README.md",
    "AFTER_EVENT.md",
    "00_Start_Here.ipynb",
    "01_GH200",
    "02_PhysicsNeMo",
    "labs",
    "LICENSE",
    "PROVENANCE.md",
    "course-release.json",
]
REQUIRED_FILES = [
    "README.md",
    "00_Start_Here.ipynb",
    "01_GH200/01_CPU_Compile_and_Tune.ipynb",
    "01_GH200/02_GPU_Memory_Profile.ipynb",
    "02_PhysicsNeMo/01_Projectile_PINN.ipynb",
    "02_PhysicsNeMo/02_Poisson_FNO.ipynb",
    "02_PhysicsNeMo/optional/FNO_Mode_Ablation.ipynb",
    "labs/gh200/blas/Makefile",
    "labs/gh200/blas/dgemm.c",
    "labs/gh200/cuda_memory/explicit.cu",
    "labs/gh200/cuda_memory/managed.cu",
    "labs/gh200/cuda_memory/hmm.cu",
    "labs/projectile/images/projectile.svg",
    "labs/projectile/images/physicsnemo_sym_workflow.webp",
    "labs/poisson_fno/images/fno_data_flow.svg",
]
FORBIDDEN_TOP_LEVEL = {"assets", "container", "operations", "tools"}
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_LINK = re.compile(r"(?:href|src)=[\"']([^\"']+)[\"']", re.I)
SHELL_NETWORK = re.compile(
    r"(?im)(?:^|[;&|]\s*)(?:sudo\s+)?(?:"
    r"apt(?:-get)?|pip3?|python3?\s+-m\s+pip|"
    r"git\s+(?:clone|pull|fetch|submodule)|wget|curl"
    r")(?:\s|$)"
)
PYTHON_NETWORK = re.compile(
    r"(?m)^\s*(?:from|import)\s+(?:"
    r"requests|urllib|httpx|aiohttp|gdown|ftplib"
    r")(?:\.|\s|$)|"
    r"\b(?:torch\.hub|from_pretrained|urlopen|urlretrieve)\s*\("
)
HTTP_LITERAL = re.compile(r"https?://", re.I)


def fail(message: str) -> None:
    print(f"FAIL  {message}")
    raise SystemExit(1)


def notebook_text(path: Path, kind: str) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"{path}: notebook JSON 오류: {error}")
    cells = data.get("cells")
    if not isinstance(cells, list):
        fail(f"{path}: cells 목록이 없습니다")
    pieces: List[str] = []
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            fail(f"{path}: cell {index}가 객체가 아닙니다")
        if cell.get("cell_type") != kind:
            continue
        source = cell.get("source", "")
        text = "".join(source) if isinstance(source, list) else str(source)
        pieces.append(text)
        if kind == "code":
            python_text = text
            if (
                path.name == "00_Start_Here.ipynb"
                and cell.get("id") == "start-nvidia-smi-code"
                and text.strip() == "!nvidia-smi"
            ):
                python_text = "pass\n"
            try:
                compile(python_text, f"{path}:cell-{index}", "exec")
            except SyntaxError as error:
                fail(f"{path}: cell {index} Python 문법 오류: {error}")
            if cell.get("outputs") or cell.get("execution_count") is not None:
                fail(f"{path}: cell {index} 실행 결과가 남아 있습니다")
    return "\n".join(pieces)


def resolve_local(root: Path, source: Path, raw: str) -> Optional[Path]:
    target = raw.strip().strip("<>")
    if not target or target.startswith("#"):
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith(("mailto:", "data:")):
        return None
    path = unquote(parsed.path)
    if not path:
        return None
    candidate = (source.parent / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        fail(f"{source.relative_to(root)} 링크가 release 밖을 가리킵니다: {raw}")
    return candidate


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir() or root.is_symlink():
        fail(f"검증 대상이 안전한 폴더가 아닙니다: {root}")

    manifest_path = root / "course-release.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"course-release.json 오류: {error}")

    if manifest.get("schema_version") != 2:
        fail("course-release.json schema_version은 2여야 합니다")
    if manifest.get("participant_entry") != "00_Start_Here.ipynb":
        fail("participant_entry는 00_Start_Here.ipynb여야 합니다")
    if manifest.get("participant_paths") != EXPECTED_PATHS:
        fail("participant_paths가 승인된 참가자 동선과 다릅니다")
    hashes = manifest.get("compatible_sif_sha256")
    if (
        not isinstance(hashes, list)
        or not hashes
        or any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value) for value in hashes)
        or len(set(hashes)) != len(hashes)
    ):
        fail("compatible_sif_sha256에 중복 없는 SHA256 값이 필요합니다")

    runtime = manifest.get("required_runtime")
    if not isinstance(runtime, dict):
        fail("required_runtime 객체가 없습니다")
    required_keys = {"image", "platform", "components", "commands", "python_imports", "capabilities"}
    if set(runtime) != required_keys:
        fail(f"required_runtime 필드가 정확하지 않습니다: {sorted(runtime)}")
    component_keys = {
        "physicsnemo", "nvhpc", "nvpl", "openblas", "nvbandwidth",
        "boost_program_options", "cuda_compiler", "nsight_systems",
    }
    if set(runtime.get("components", {})) != component_keys:
        fail("required_runtime.components가 전체 실습 의존성을 기록하지 않았습니다")
    if runtime.get("platform") != "linux/arm64":
        fail("participant runtime platform은 linux/arm64여야 합니다")
    if set(runtime.get("capabilities", [])) != EXPECTED_CAPABILITIES:
        fail("required_runtime.capabilities가 ARM64/GH200/R570 forward compatibility/SSH tunnel/offline 계약과 다릅니다")

    for name in EXPECTED_PATHS:
        if not (root / name).exists():
            fail(f"필수 participant path가 없습니다: {name}")
    present_top = {path.name for path in root.iterdir() if not path.name.startswith(".")}
    if FORBIDDEN_TOP_LEVEL.intersection(present_top):
        fail(f"운영/중복 자료가 참가자 release에 섞였습니다: {sorted(FORBIDDEN_TOP_LEVEL.intersection(present_top))}")
    if present_top != set(EXPECTED_PATHS):
        fail(f"참가자 release 최상위가 manifest와 다릅니다: {sorted(present_top)}")

    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            fail(f"필수 regular file이 없습니다: {relative}")

    all_files: List[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(ord(character) < 32 for character in str(relative)):
            fail(f"제어 문자가 든 경로는 허용하지 않습니다: {relative!r}")
        if path.is_symlink():
            fail(f"심볼릭 링크는 participant release에 허용하지 않습니다: {relative}")
        if path.is_file():
            if path.stat().st_size > 64 * 1024 * 1024:
                fail(f"64 MiB를 넘는 파일은 participant release에 허용하지 않습니다: {relative}")
            all_files.append(path)
        elif not path.is_dir():
            fail(f"regular file/directory가 아닌 항목입니다: {relative}")

    notebooks = sorted(root.rglob("*.ipynb"))
    runtime_sources: List[Tuple[Path, str]] = []
    documents: List[Tuple[Path, str]] = []
    for path in notebooks:
        runtime_sources.append((path, notebook_text(path, "code")))
        documents.append((path, notebook_text(path, "markdown")))

    for path in all_files:
        suffix = path.suffix.lower()
        if suffix == ".py":
            text = path.read_text(encoding="utf-8")
            try:
                ast.parse(text, filename=str(path))
            except SyntaxError as error:
                fail(f"{path.relative_to(root)} Python 문법 오류: {error}")
            runtime_sources.append((path, text))
        elif suffix in {".sh", ".c", ".cu"} or path.name == "Makefile":
            runtime_sources.append((path, path.read_text(encoding="utf-8", errors="replace")))
        if suffix == ".md":
            documents.append((path, path.read_text(encoding="utf-8")))

    violations: List[str] = []
    for path, text in runtime_sources:
        if SHELL_NETWORK.search(text) or PYTHON_NETWORK.search(text) or HTTP_LITERAL.search(text):
            violations.append(str(path.relative_to(root)))
    if violations:
        fail("계산 노드 runtime 다운로드/외부 통신 흔적: " + ", ".join(sorted(set(violations))))

    missing_links: List[str] = []
    for path, text in documents:
        for raw in MARKDOWN_LINK.findall(text) + HTML_LINK.findall(text):
            target = resolve_local(root, path, raw)
            if target is not None and not target.exists():
                missing_links.append(f"{path.relative_to(root)} -> {raw}")
    if missing_links:
        fail("깨진 participant 링크: " + "; ".join(missing_links))

    print(f"PASS  participant release closure ({len(all_files)} files, {len(notebooks)} notebooks)")
    print("PASS  runtime install/download/external-network calls: 0")
    print("PASS  local links, Python syntax, notebook JSON/output state")
    print("KSC2026_PARTICIPANT_RELEASE_VALID=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
