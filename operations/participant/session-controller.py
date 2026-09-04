#!/usr/bin/env python3
"""KSC 2026 공용 Slurm/Jupyter 세션 제어기.

현재 SSH 인증 계정을 ``id -un``으로 확인하고 GH200 한 개를 Slurm에 요청한다.
계산 노드와 물리 GPU는 Slurm이 선택하며, READY 상태가 된 뒤 실제 연결 정보를 출력한다.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import http.client
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
DEFAULT_SITE_CONFIG = PACKAGE_ROOT / "config" / "site.env"
SCRATCH_ROOT = Path("/scratch")
ACTIVE_STATES = {"PENDING", "CONFIGURING", "RUNNING", "COMPLETING", "SUSPENDED"}
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# This is input/output sanitization, not a scheduler allowlist.  Slurm remains
# free to choose any node in the configured GPU partition.
# Accept one scheduler-returned DNS label without encoding the site's node naming scheme.
NODE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
LOGIN_HOST_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
JOB_RE = re.compile(r"^[1-9][0-9]*$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
COURSE_ENTRY = "00_Start_Here.ipynb"
COURSE_LANDING = "README.md"
SHARED_COMMAND = "/scratch/hackathon/ksc2026/bin/ksc2026"
LOCAL_JUPYTER_PORT = 8888
ALLOWED_PERSONAL_SCRATCH_MODES = {0o700, 0o750, 0o755}

ALLOWED_SITE_KEYS = {
    "KSC_SHARED_ROOT",
    "KSC_LOGIN_HOST",
    "KSC_PARTITION",
    "KSC_JOB_COMMENT",
    "KSC_GRES_NAME",
    "KSC_TIME_LIMIT",
    "KSC_READY_TIMEOUT",
    "KSC_APPTAINER",
    "KSC_IMAGE",
    "KSC_IMAGE_SHA256",
    "KSC_SIF_SHA256",
    "KSC_COURSE_RELEASE_ROOT",
    "KSC_COURSE_RELEASE",
    "KSC_COURSE_REPOSITORY",
    "KSC_COURSE_REF",
    "KSC_COURSE_SOURCE",
    "KSC_RUNTIME_COMPATIBILITY",
    "KSC_JOB_SCRIPT",
    "KSC_STATE_ROOT",
    "KSC_WORKSPACE_ROOT",
    "KSC_LOG_ROOT",
    "KSC_CPUS_PER_TASK",
    "KSC_MEMORY",
}
REQUIRED_SITE_KEYS = {
    "KSC_SHARED_ROOT",
    "KSC_LOGIN_HOST",
    "KSC_APPTAINER",
    "KSC_IMAGE",
    "KSC_IMAGE_SHA256",
    "KSC_COURSE_RELEASE_ROOT",
    "KSC_COURSE_RELEASE",
    "KSC_RUNTIME_COMPATIBILITY",
    "KSC_JOB_SCRIPT",
}


class SessionError(RuntimeError):
    """안전하게 자동 진행할 수 없을 때 발생한다."""


@dataclass(frozen=True)
class Course:
    source: Path
    commit: str
    runtime_compatibility: str
    sif_sha256: str


def current_username() -> str:
    """환경변수 USER가 아니라 id -un이 확인한 인증 계정을 사용한다."""
    process = subprocess.run(
        ["id", "-un"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    username = process.stdout.strip()
    if process.returncode or not USERNAME_RE.fullmatch(username):
        raise SessionError("id -un으로 현재 인증 계정을 확인할 수 없습니다")
    return username


def mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def directory_open_flags() -> int:
    """Return flags required for component-by-component, no-follow traversal."""
    if (
        not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or os.open not in os.supports_dir_fd
        or os.mkdir not in os.supports_dir_fd
    ):
        raise SessionError("이 시스템은 개인 /scratch 경로의 안전한 검증을 지원하지 않습니다")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


@contextmanager
def canonical_directory_fd(path: Path):
    """Open every absolute path component as a real directory, never a symlink."""
    candidate = Path(path)
    normalized = Path(os.path.abspath(str(candidate)))
    if not candidate.is_absolute() or candidate != normalized:
        raise SessionError(f"정규화된 절대 디렉터리 경로가 아닙니다: {candidate}")
    flags = directory_open_flags()
    descriptor: int | None = None
    try:
        descriptor = os.open(candidate.anchor, flags)
        for component in candidate.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise SessionError(
            f"심볼릭 링크 없이 실제 디렉터리로 확인할 수 없습니다: {candidate}"
        ) from exc
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def validate_personal_scratch(path: Path) -> os.stat_result:
    """Validate the administrator-provisioned /scratch/<id-un> directory."""
    with canonical_directory_fd(path) as descriptor:
        directory_stat = os.fstat(descriptor)
    permissions = stat.S_IMODE(directory_stat.st_mode)
    if not stat.S_ISDIR(directory_stat.st_mode):
        raise SessionError(f"개인 scratch 경로가 실제 디렉터리가 아닙니다: {path}")
    if directory_stat.st_uid != os.getuid():
        raise SessionError(f"개인 scratch 경로가 현재 계정 소유가 아닙니다: {path}")
    if permissions not in ALLOWED_PERSONAL_SCRATCH_MODES:
        raise SessionError(
            "개인 scratch 경로는 owner rwx이고 그룹·전체 사용자 쓰기가 금지되어야 "
            f"합니다(허용 mode=0700/0750/0755, 실제 mode={permissions:04o}): {path}"
        )
    return directory_stat


def private_relative_parts(path: Path, personal_root: Path) -> tuple[str, ...]:
    candidate = Path(path)
    root = Path(personal_root)
    if (
        not candidate.is_absolute()
        or not root.is_absolute()
        or candidate != Path(os.path.abspath(str(candidate)))
        or root != Path(os.path.abspath(str(root)))
    ):
        raise SessionError(f"개인 저장 경로가 정규화된 절대 경로가 아닙니다: {candidate}")
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise SessionError(f"개인 저장 경로가 계정 scratch 밖을 가리킵니다: {candidate}") from exc
    if not relative.parts:
        raise SessionError(f"개인 scratch root 자체를 비공개 하위 경로로 사용할 수 없습니다: {candidate}")
    return relative.parts


def walk_private_dir(path: Path, personal_root: Path, *, create: bool) -> bool:
    """Validate, or safely create, each private component below personal_root."""
    parts = private_relative_parts(path, personal_root)
    with canonical_directory_fd(personal_root) as root_descriptor:
        root_stat = os.fstat(root_descriptor)
        permissions = stat.S_IMODE(root_stat.st_mode)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or root_stat.st_uid != os.getuid()
            or permissions not in ALLOWED_PERSONAL_SCRATCH_MODES
        ):
            raise SessionError(f"개인 scratch root가 안전하지 않습니다: {personal_root}")
        descriptor = os.dup(root_descriptor)
        current = Path(personal_root)
        try:
            for component in parts:
                current /= component
                try:
                    child = os.open(component, directory_open_flags(), dir_fd=descriptor)
                except FileNotFoundError:
                    if not create:
                        return False
                    try:
                        os.mkdir(component, 0o700, dir_fd=descriptor)
                    except FileExistsError:
                        # A concurrent creator is acceptable only if the no-follow open below
                        # proves that it created the exact private directory we require.
                        pass
                    except OSError as exc:
                        raise SessionError(f"비공개 디렉터리를 만들 수 없습니다: {current}") from exc
                    try:
                        child = os.open(component, directory_open_flags(), dir_fd=descriptor)
                    except OSError as exc:
                        raise SessionError(
                            f"새 비공개 디렉터리를 안전하게 확인할 수 없습니다: {current}"
                        ) from exc
                except OSError as exc:
                    raise SessionError(
                        f"비공개 경로에 실제 디렉터리가 아닌 항목이 있습니다: {current}"
                    ) from exc
                child_stat = os.fstat(child)
                child_mode = stat.S_IMODE(child_stat.st_mode)
                if (
                    not stat.S_ISDIR(child_stat.st_mode)
                    or child_stat.st_uid != os.getuid()
                    or child_mode != 0o700
                ):
                    os.close(child)
                    raise SessionError(
                        "기존 비공개 디렉터리는 현재 계정 소유 mode 0700이어야 "
                        f"합니다(uid={child_stat.st_uid}, mode={child_mode:04o}): {current}"
                    )
                os.close(descriptor)
                descriptor = child
        finally:
            os.close(descriptor)
    return True


def validate_private_dir(path: Path, personal_root: Path) -> bool:
    """Return False only when a safe path suffix has not been created yet."""
    return walk_private_dir(path, personal_root, create=False)


def ensure_private_dir(path: Path, personal_root: Path) -> None:
    walk_private_dir(path, personal_root, create=True)


def require_private_control_stat(
    file_stat: os.stat_result, path: Path, label: str, *, require_mode: bool = True
) -> None:
    permissions = stat.S_IMODE(file_stat.st_mode)
    if (
        not stat.S_ISREG(file_stat.st_mode)
        or file_stat.st_uid != os.getuid()
        or file_stat.st_nlink != 1
        or (require_mode and permissions != 0o600)
    ):
        raise SessionError(
            f"{label}는 현재 계정 소유 일반 파일 mode 0600 nlink 1이어야 "
            f"합니다(uid={file_stat.st_uid}, mode={permissions:04o}, "
            f"nlink={file_stat.st_nlink}): {path}"
        )


def open_private_control_file(path: Path, label: str) -> int | None:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SessionError(f"{label}를 심볼릭 링크 없이 열 수 없습니다: {path}") from exc
    try:
        require_private_control_stat(os.fstat(descriptor), path, label)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def validate_private_control_file(path: Path, label: str) -> bool:
    descriptor = open_private_control_file(path, label)
    if descriptor is None:
        return False
    os.close(descriptor)
    return True


def read_private_text(path: Path, label: str, *, encoding: str) -> str | None:
    descriptor = open_private_control_file(path, label)
    if descriptor is None:
        return None
    try:
        with os.fdopen(descriptor, encoding=encoding) as handle:
            return handle.read()
    except (OSError, UnicodeError) as exc:
        raise SessionError(f"{label}를 읽을 수 없습니다: {path}: {exc}") from exc


def validate_private_storage(paths: dict[str, Path]) -> os.stat_result:
    """Validate the personal root and every existing controller-managed directory."""
    personal_root = paths["personal_root"]
    personal_stat = validate_personal_scratch(personal_root)
    for key in ("state", "workspaces", "logs", "archive"):
        validate_private_dir(paths[key], personal_root)
    for key, label in (
        ("metadata", "세션 metadata"),
        ("token", "Jupyter token"),
        ("ready", "Jupyter ready 상태"),
        ("lock", "세션 lock"),
        ("active_workspace", "현재 작업공간 상태"),
    ):
        validate_private_control_file(paths[key], label)
    return personal_stat


def require_plain_file(path: Path, label: str, *, private: bool = False) -> None:
    if path.is_symlink() or not path.is_file():
        raise SessionError(f"{label} 파일을 안전하게 읽을 수 없습니다: {path}")
    st = path.stat()
    if private:
        if st.st_uid != os.getuid() or mode(path) != 0o600:
            raise SessionError(f"{label}는 현재 계정 소유 mode 0600이어야 합니다: {path}")
    elif mode(path) & 0o022:
        raise SessionError(f"{label}는 그룹·전체 사용자에게 쓰기 허용되면 안 됩니다: {path}")


def parse_site_config(path: Path = DEFAULT_SITE_CONFIG) -> dict[str, str]:
    require_plain_file(path, "사이트 설정")
    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SessionError(f"사이트 설정 {line_number}행에 '='가 없습니다")
        key, value = line.split("=", 1)
        if key not in ALLOWED_SITE_KEYS:
            raise SessionError(f"사이트 설정 {line_number}행에 알 수 없는 항목이 있습니다: {key}")
        if key in values:
            raise SessionError(f"사이트 설정 항목이 중복됩니다: {key}")
        if any(mark in value for mark in ("\n", "\r", "`", "$")):
            raise SessionError(f"사이트 설정 값이 안전하지 않습니다: {key}")
        values[key] = value
    missing = sorted(key for key in REQUIRED_SITE_KEYS if not values.get(key))
    if missing:
        raise SessionError("사이트 설정 필수 항목이 없습니다: " + ", ".join(missing))
    return values


def resolve_config_path(value: str, cfg_path: Path, username: str) -> Path:
    expanded = value.replace("{user}", username)
    path = Path(expanded)
    if not path.is_absolute():
        path = cfg_path.parent / path
    return path.resolve(strict=False)


def resolve_private_config_path(value: str, cfg_path: Path, username: str) -> Path:
    """Normalize private paths lexically so validation, not resolve(), handles links."""
    expanded = value.replace("{user}", username)
    path = Path(expanded)
    if not path.is_absolute():
        path = cfg_path.parent / path
    return Path(os.path.abspath(str(path)))


def require_under(path: Path, root: Path, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SessionError(f"{label}가 허용된 경로 밖을 가리킵니다: {path}") from exc


def require_readonly_tree(root: Path, label: str) -> None:
    if not root.is_dir():
        raise SessionError(f"{label} 폴더를 읽을 수 없습니다: {root}")
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        if current_path.is_symlink() or mode(current_path) & 0o022:
            raise SessionError(f"{label}에 쓰기 가능하거나 링크인 폴더가 있습니다: {current_path}")
        for name in dirs + files:
            item = current_path / name
            if item.is_symlink():
                raise SessionError(f"{label} 안에는 심볼릭 링크를 둘 수 없습니다: {item}")
            if mode(item) & 0o022:
                raise SessionError(f"{label} 안에 쓰기 가능한 항목이 있습니다: {item}")
            if name in files and not item.is_file():
                raise SessionError(f"{label} 안에 일반 파일이 아닌 항목이 있습니다: {item}")


def read_marker(path: Path, pattern: re.Pattern[str], label: str) -> str:
    require_plain_file(path, label)
    value = path.read_text(encoding="utf-8").strip()
    if not pattern.fullmatch(value):
        raise SessionError(f"{label} 형식이 올바르지 않습니다: {path}")
    return value


def read_course(config: dict[str, str], cfg_path: Path, username: str) -> Course:
    shared_root = resolve_config_path(config["KSC_SHARED_ROOT"], cfg_path, username)
    release_root = resolve_config_path(config["KSC_COURSE_RELEASE_ROOT"], cfg_path, username)
    image = resolve_config_path(config["KSC_IMAGE"], cfg_path, username)
    source_config = resolve_config_path(config["KSC_COURSE_RELEASE"], cfg_path, username)
    require_under(release_root, shared_root, "강의 release root")
    require_under(image, shared_root, "SIF")
    if not shared_root.is_dir() or mode(shared_root) & 0o022:
        raise SessionError(f"중앙 읽기 전용 root가 안전하지 않습니다: {shared_root}")
    if image.is_symlink() or not image.is_file() or not os.access(image, os.R_OK) or mode(image) & 0o022:
        raise SessionError(f"고정 SIF를 안전하게 읽을 수 없습니다: {image}")
    expected_sha = config["KSC_IMAGE_SHA256"]
    if not HEX64_RE.fullmatch(expected_sha):
        raise SessionError("KSC_IMAGE_SHA256 형식이 올바르지 않습니다")
    if source_config.is_symlink():
        raise SessionError(f"고정 강의 release 경로는 심볼릭 링크일 수 없습니다: {source_config}")
    try:
        source = source_config.resolve(strict=True)
    except (FileNotFoundError, RuntimeError) as exc:
        raise SessionError(f"현재 중앙 강의 release를 확인할 수 없습니다: {source_config}") from exc
    release_root_real = release_root.resolve(strict=True)
    require_under(source, release_root_real, "현재 강의 release")
    require_readonly_tree(source, "중앙 강의 release")
    commit = read_marker(source / ".ksc2026-course-revision", HEX40_RE, "강의 commit 표식")
    runtime = (source / ".ksc2026-runtime-compatibility").read_text(encoding="utf-8").strip()
    sif_sha = read_marker(
        source / ".ksc2026-compatible-sif-sha256", HEX64_RE, "강의 SIF 호환성 표식"
    )
    if runtime != config["KSC_RUNTIME_COMPATIBILITY"]:
        raise SessionError("중앙 강의자료와 사이트 runtime compatibility가 다릅니다")
    if sif_sha != expected_sha:
        raise SessionError("중앙 강의자료가 설치된 고정 SIF와 호환되지 않습니다")
    if not (source / COURSE_ENTRY).is_file():
        raise SessionError(f"중앙 강의자료에 {COURSE_ENTRY}가 없습니다")
    if not (source / COURSE_LANDING).is_file():
        raise SessionError(f"중앙 강의자료에 {COURSE_LANDING}가 없습니다")
    verify_payload(source)
    return Course(source=source, commit=commit, runtime_compatibility=runtime, sif_sha256=sif_sha)


def verify_payload(source: Path) -> None:
    manifest = source / ".ksc2026-payload.sha256"
    require_plain_file(manifest, "강의 payload SHA256 manifest")
    seen: set[str] = set()
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if not match:
            raise SessionError(f"강의 payload manifest {line_number}행이 올바르지 않습니다")
        expected, relative = match.groups()
        pure = Path(relative)
        if pure.is_absolute() or ".." in pure.parts or relative in seen:
            raise SessionError(f"강의 payload manifest 경로가 안전하지 않습니다: {relative}")
        seen.add(relative)
        path = source / pure
        if path.is_symlink() or not path.is_file():
            raise SessionError(f"강의 payload 파일이 없습니다: {relative}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise SessionError(f"강의 payload SHA256이 다릅니다: {relative}")


def state_paths(config: dict[str, str], cfg_path: Path, username: str) -> dict[str, Path]:
    if not USERNAME_RE.fullmatch(username):
        raise SessionError(f"현재 계정 이름이 올바르지 않습니다: {username!r}")
    personal_root = SCRATCH_ROOT / username
    account_root = personal_root / "ksc2026"
    state = resolve_private_config_path(
        config.get("KSC_STATE_ROOT", str(account_root / "session")),
        cfg_path,
        username,
    )
    workspaces = resolve_private_config_path(
        config.get("KSC_WORKSPACE_ROOT", str(account_root / "workspaces")),
        cfg_path,
        username,
    )
    logs = resolve_private_config_path(
        config.get("KSC_LOG_ROOT", str(account_root / "logs")),
        cfg_path,
        username,
    )
    require_under(state, account_root, "세션 상태 경로")
    require_under(workspaces, account_root, "작업공간 경로")
    require_under(logs, account_root, "로그 경로")
    return {
        "personal_root": personal_root,
        "account_root": account_root,
        "state": state,
        "workspaces": workspaces,
        "logs": logs,
        "metadata": state / "metadata.json",
        "token": state / "token",
        "ready": state / "ready.json",
        "lock": state / "lock",
        "archive": state / "archive",
        "active_workspace": state / "active-workspace.json",
    }


@contextmanager
def session_lock(lock_dir: Path, personal_root: Path, timeout: int = 30):
    """Use a kernel-released advisory lock; no stale mkdir survives a crash."""
    lock_file = lock_dir
    ensure_private_dir(lock_file.parent, personal_root)
    flags = os.O_RDWR | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    created = False
    try:
        with canonical_directory_fd(lock_file.parent) as parent_descriptor:
            try:
                descriptor = os.open(
                    lock_file.name,
                    flags | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=parent_descriptor,
                )
                created = True
            except FileExistsError:
                descriptor = os.open(lock_file.name, flags, dir_fd=parent_descriptor)
    except OSError as exc:
        raise SessionError(f"세션 lock 파일이 안전하지 않습니다: {lock_file}") from exc
    deadline = time.monotonic() + timeout
    try:
        file_stat = os.fstat(descriptor)
        require_private_control_stat(file_stat, lock_file, "세션 lock", require_mode=not created)
        if created:
            os.fchmod(descriptor, 0o600)
        require_private_control_stat(os.fstat(descriptor), lock_file, "세션 lock")
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise SessionError("다른 시작·종료 명령이 실행 중입니다. 잠시 뒤 다시 시도하세요")
                time.sleep(0.5)
        os.ftruncate(descriptor, 0)
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def atomic_json(path: Path, data: dict[str, object]) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temp.open("x", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def read_json(path: Path) -> dict[str, object] | None:
    descriptor = open_private_control_file(path, "세션 상태")
    if descriptor is None:
        return None
    try:
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionError(f"세션 상태를 읽을 수 없습니다: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SessionError(f"세션 상태는 JSON object여야 합니다: {path}")
    return value


def run(command: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and process.returncode:
        detail = process.stderr.strip() or process.stdout.strip() or f"exit {process.returncode}"
        raise SessionError(f"명령 실행 실패: {shlex.join(command)}\n{detail}")
    return process


def prepare_workspace(course: Course, paths: dict[str, Path], *, fresh: bool = False) -> Path:
    personal_root = paths["personal_root"]
    ensure_private_dir(paths["workspaces"], personal_root)
    suffix = ""
    if fresh:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = f"-fresh-{stamp}-{os.urandom(4).hex()}"
    workspace = paths["workspaces"] / f"course-{course.commit[:12]}{suffix}"
    marker = workspace / ".ksc2026-workspace.json"
    if validate_private_dir(workspace, personal_root):
        metadata = read_json(marker)
        if not metadata or metadata.get("commit") != course.commit:
            raise SessionError(f"기존 작업공간의 출처를 확인할 수 없습니다: {workspace}")
        return workspace
    temporary = paths["workspaces"] / f".course-{course.commit[:12]}.{os.getpid()}.tmp"
    if validate_private_dir(temporary, personal_root):
        raise SessionError(f"작업공간 임시 경로가 이미 있습니다: {temporary}")
    try:
        ensure_private_dir(temporary, personal_root)
        shutil.copytree(course.source, temporary, symlinks=False, dirs_exist_ok=True)
        for current, dirs, files in os.walk(temporary):
            descriptor = os.open(current, directory_open_flags())
            try:
                current_stat = os.fstat(descriptor)
                if current_stat.st_uid != os.getuid():
                    raise SessionError(f"복사한 작업공간 디렉터리 소유자가 다릅니다: {current}")
                os.fchmod(descriptor, 0o700)
            finally:
                os.close(descriptor)
            for name in dirs:
                directory = Path(current) / name
                descriptor = os.open(directory, directory_open_flags())
                try:
                    directory_stat = os.fstat(descriptor)
                    if directory_stat.st_uid != os.getuid():
                        raise SessionError(f"복사한 작업공간 디렉터리 소유자가 다릅니다: {directory}")
                    os.fchmod(descriptor, 0o700)
                finally:
                    os.close(descriptor)
            for name in files:
                item = Path(current) / name
                flags = os.O_RDONLY | os.O_NOFOLLOW
                if hasattr(os, "O_CLOEXEC"):
                    flags |= os.O_CLOEXEC
                descriptor = os.open(item, flags)
                try:
                    item_stat = os.fstat(descriptor)
                    if not stat.S_ISREG(item_stat.st_mode) or item_stat.st_uid != os.getuid():
                        raise SessionError(f"복사한 작업공간 파일이 안전하지 않습니다: {item}")
                    os.fchmod(descriptor, 0o600)
                finally:
                    os.close(descriptor)
        atomic_json(
            temporary / ".ksc2026-workspace.json",
            {
                "schema_version": 1,
                "commit": course.commit,
                "runtime_compatibility": course.runtime_compatibility,
                "sif_sha256": course.sif_sha256,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        os.replace(temporary, workspace)
    except BaseException:
        if temporary.is_dir() and not temporary.is_symlink():
            shutil.rmtree(temporary)
        raise
    return workspace


def select_workspace(course: Course, paths: dict[str, Path]) -> Path:
    active = read_json(paths["active_workspace"])
    if active and active.get("commit") == course.commit:
        workspace = Path(str(active.get("workspace", "")))
        require_under(workspace, paths["workspaces"], "현재 작업공간")
        workspace_exists = validate_private_dir(workspace, paths["personal_root"])
        marker = read_json(workspace / ".ksc2026-workspace.json") if workspace_exists else None
        if marker and marker.get("commit") == course.commit:
            return workspace
        raise SessionError("현재 작업공간 상태가 안전하지 않습니다")
    workspace = prepare_workspace(course, paths)
    set_active_workspace(course, workspace, paths)
    return workspace


def set_active_workspace(course: Course, workspace: Path, paths: dict[str, Path]) -> None:
    require_under(workspace, paths["workspaces"], "새 작업공간")
    atomic_json(
        paths["active_workspace"],
        {"schema_version": 1, "commit": course.commit, "workspace": str(workspace)},
    )


def query_job(job_id: str) -> dict[str, str] | None:
    if not JOB_RE.fullmatch(job_id):
        raise SessionError(f"저장된 Job ID가 올바르지 않습니다: {job_id!r}")
    process = run(
        ["squeue", "--noheader", f"--jobs={job_id}", "--format=%u|%T|%N|%j"],
        check=False,
    )
    if process.returncode:
        detail = process.stderr.strip() or process.stdout.strip() or f"exit {process.returncode}"
        raise SessionError(f"Slurm Job {job_id}를 확인할 수 없어 새 Job을 시작하지 않습니다\n{detail}")
    lines = [line for line in process.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines) != 1:
        raise SessionError(f"Job {job_id} 조회 결과가 하나가 아닙니다")
    fields = (lines[0].split("|", 3) + ["", "", "", ""])[:4]
    return {
        "job_id": job_id,
        "owner": fields[0].strip(),
        "state": fields[1].strip().upper(),
        "node": fields[2].strip(),
        "name": fields[3].strip(),
    }


def query_named_jobs(username: str) -> list[dict[str, str]]:
    """Return every active job with this account's exact managed job name."""
    if not USERNAME_RE.fullmatch(username):
        raise SessionError(f"현재 계정 이름이 올바르지 않습니다: {username!r}")
    job_name = f"ksc26-jlab-{username}"
    process = run(
        [
            "squeue",
            "--noheader",
            f"--user={username}",
            f"--name={job_name}",
            "--states=PENDING,CONFIGURING,RUNNING,COMPLETING,SUSPENDED",
            "--format=%A|%u|%T|%N|%j",
        ],
        check=False,
    )
    if process.returncode:
        detail = process.stderr.strip() or process.stdout.strip() or f"exit {process.returncode}"
        raise SessionError(f"현재 KSC2026 Job 목록을 확인할 수 없어 자동 진행하지 않습니다\n{detail}")
    jobs: list[dict[str, str]] = []
    for line in process.stdout.splitlines():
        if not line.strip():
            continue
        fields = (line.split("|", 4) + ["", "", "", "", ""])[:5]
        job_id, owner, state, node, name = (value.strip() for value in fields)
        if (
            not JOB_RE.fullmatch(job_id)
            or owner != username
            or name != job_name
            or state.upper() not in ACTIVE_STATES
        ):
            raise SessionError(f"KSC2026 Job 조회 결과가 불명확합니다: {line}")
        jobs.append(
            {"job_id": job_id, "owner": owner, "state": state.upper(), "node": node, "name": name}
        )
    return jobs


def require_named_job_consistency(
    metadata: dict[str, object] | None, jobs: list[dict[str, str]]
) -> None:
    """Fail closed on orphan or duplicate managed jobs before any mutation."""
    if metadata is None:
        if jobs:
            ids = ", ".join(job["job_id"] for job in jobs)
            raise SessionError(
                f"상태 파일 없이 실행 중인 KSC2026 Job이 있습니다({ids}). "
                "새 Job을 만들거나 자동 종료하지 않습니다. 운영자 확인이 필요합니다"
            )
        return
    stored = str(metadata.get("job_id", ""))
    if not jobs:
        return
    if len(jobs) != 1 or jobs[0]["job_id"] != stored:
        ids = ", ".join(job["job_id"] for job in jobs)
        raise SessionError(
            f"저장 Job과 실제 KSC2026 Job 목록이 다릅니다(stored={stored}, active={ids}). "
            "중복 Job을 자동 처리하지 않습니다"
        )


def authenticated_http_ready(node: str, port: int, token: str) -> bool:
    """Require a token-authenticated Jupyter status response from the compute node."""
    if not NODE_RE.fullmatch(node) or not 1024 <= port <= 65535:
        return False
    if not re.fullmatch(r"[0-9a-f]{48}", token):
        return False
    connection = None
    try:
        connection = http.client.HTTPConnection(node, port, timeout=3)
        connection.request("GET", "/api/status", headers={"Authorization": "token " + token})
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        return response.status == 200 and isinstance(payload, dict)
    except (OSError, ValueError, json.JSONDecodeError, http.client.HTTPException):
        return False
    finally:
        if connection is not None:
            connection.close()


def session_status(
    metadata: dict[str, object] | None,
    username: str,
    paths: dict[str, Path],
) -> tuple[str, dict[str, str] | None]:
    if not metadata:
        return "ABSENT", None
    if (
        metadata.get("schema_version") != 2
        or metadata.get("account") != username
        or metadata.get("gpu_count") != 1
    ):
        raise SessionError(
            "저장된 세션 정보가 현재 공용 1-GPU 형식과 다릅니다. "
            "기존 Job을 운영자가 확인한 뒤 새 세션을 시작하세요"
        )
    job_id = str(metadata.get("job_id", ""))
    if not JOB_RE.fullmatch(job_id):
        return "STALE", None
    job = query_job(job_id)
    if not job:
        return "STALE", None
    expected_name = f"ksc26-jlab-{username}"
    if job["owner"] != username or job["name"] != expected_name:
        raise SessionError(f"저장 Job {job_id}의 소유자 또는 이름이 현재 세션과 다릅니다")
    if job["state"] == "RUNNING" and not NODE_RE.fullmatch(job["node"]):
        raise SessionError(f"Job {job_id}의 계산 노드 이름을 안전하게 확인할 수 없습니다: {job['node']}")
    ready = read_json(paths["ready"])
    token_text = read_private_text(paths["token"], "Jupyter token", encoding="ascii")
    if ready and token_text is not None and job["state"] == "RUNNING":
        token = token_text.strip()
        gpu_index = ready.get("gpu_index")
        ready_port = ready.get("port")
        ready_node = ready.get("node")
        endpoint_matches = (
            str(ready.get("job_id")) == job_id
            and ready.get("course_commit") == metadata.get("course_commit")
            and ready_node == job["node"]
            and NODE_RE.fullmatch(str(ready_node)) is not None
            and type(gpu_index) is int
            and 0 <= gpu_index <= 3
            and ready_port == 18880 + gpu_index
        )
        if endpoint_matches and authenticated_http_ready(str(ready_node), int(ready_port), token):
            return "READY", job
    if job["state"] == "RUNNING":
        return "STARTING", job
    return job["state"], job


def build_sbatch(
    config: dict[str, str],
    cfg_path: Path,
    username: str,
    paths: dict[str, Path],
    workspace: Path,
    course: Course,
) -> list[str]:
    partition = config.get("KSC_PARTITION", "gpu")
    comment = config.get("KSC_JOB_COMMENT", "jupyter")
    gres = config.get("KSC_GRES_NAME", "nvidia_gh200_120gb")
    walltime = config.get("KSC_TIME_LIMIT", "1-00:00:00")
    if walltime != "1-00:00:00":
        raise SessionError("실습 Job 시간은 24시간(1-00:00:00)으로 고정해야 합니다")
    for label, value in (("partition", partition), ("comment", comment), ("GRES", gres)):
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
            raise SessionError(f"{label} 설정이 안전하지 않습니다: {value!r}")
    image = resolve_config_path(config["KSC_IMAGE"], cfg_path, username)
    apptainer = resolve_config_path(config["KSC_APPTAINER"], cfg_path, username)
    job_script = resolve_config_path(config["KSC_JOB_SCRIPT"], cfg_path, username)
    exports = {
        "KSC_STATE_DIR": str(paths["state"]),
        "KSC_WORK_DIR": str(workspace),
        "KSC_LOG_DIR": str(paths["logs"]),
        "KSC_IMAGE": str(image),
        "KSC_IMAGE_SHA256": course.sif_sha256,
        "KSC_EXPECTED_GPU_COUNT": "1",
        "KSC_APPTAINER": str(apptainer),
        "KSC_COURSE_COMMIT": course.commit,
        "KSC_RUNTIME_COMPATIBILITY": course.runtime_compatibility,
        "KSC_ENTRY_NOTEBOOK": COURSE_ENTRY,
        "KSC_LANDING_PAGE": COURSE_LANDING,
        "KSC_JOB_READY_TIMEOUT": config.get("KSC_READY_TIMEOUT", "900"),
    }
    if any("," in value or "\n" in value for value in exports.values()):
        raise SessionError("Slurm 전달 값에 쉼표 또는 줄바꿈을 사용할 수 없습니다")
    export_arg = ",".join(f"{key}={value}" for key, value in exports.items())
    command = [
        "sbatch",
        "--parsable",
        f"--partition={partition}",
        f"--comment={comment}",
        f"--job-name=ksc26-jlab-{username}",
        "--nodes=1",
        "--ntasks=1",
        f"--gres=gpu:{gres}:1",
        "--time=1-00:00:00",
        f"--chdir=/scratch/{username}",
        f"--output={paths['logs'] / 'job-%j.log'}",
        f"--export={export_arg}",
    ]
    cpus = config.get("KSC_CPUS_PER_TASK", "")
    memory = config.get("KSC_MEMORY", "")
    if cpus:
        if not cpus.isdigit() or int(cpus) < 1:
            raise SessionError("KSC_CPUS_PER_TASK가 올바르지 않습니다")
        command.append(f"--cpus-per-task={cpus}")
    if memory:
        if not re.fullmatch(r"[1-9][0-9]*[KMGTP]?", memory, re.IGNORECASE):
            raise SessionError("KSC_MEMORY가 올바르지 않습니다")
        command.append(f"--mem={memory}")
    # The scheduler chooses the node.  Every authenticated user requests one
    # non-exclusive GH200; this command intentionally has no node allow/exclude list.
    command.append(str(job_script))
    return command


def wait_ready(
    metadata: dict[str, object], username: str, paths: dict[str, Path], timeout: int
) -> str:
    deadline = time.monotonic() + timeout
    last = "SUBMITTED"
    while time.monotonic() < deadline:
        state, _ = session_status(metadata, username, paths)
        last = state
        if state == "READY":
            return state
        if state not in ACTIVE_STATES | {"STARTING"}:
            logs = sorted(paths["logs"].glob("job-*.log"), key=lambda p: p.stat().st_mtime)
            tail = ""
            if logs:
                tail = "\n".join(logs[-1].read_text(errors="replace").splitlines()[-20:])
            raise SessionError(f"Jupyter Job이 준비 전에 종료됐습니다(state={state})\n{tail}")
        time.sleep(2)
    raise SessionError(f"Jupyter 준비 시간이 초과되었습니다(state={last}). 같은 명령으로 다시 확인하세요")


def emit_session(
    state: str,
    config: dict[str, str],
    username: str,
    metadata: dict[str, object] | None,
    paths: dict[str, Path],
) -> None:
    if state != "READY":
        print("KSC2026 세션 상태")
        print(f"상태: {state}")
        print(f"현재 계정: {username}")
        print(f"Job ID: {metadata.get('job_id', '') if metadata else ''}")
        if state == "ABSENT":
            print(f"새 세션 시작: {SHARED_COMMAND}")
        return

    token_text = read_private_text(paths["token"], "Jupyter token", encoding="ascii")
    if token_text is None:
        raise SessionError("Jupyter token 파일이 없습니다")
    token = token_text.strip()
    if not re.fullmatch(r"[0-9a-f]{48}", token):
        raise SessionError("Jupyter token 파일이 올바르지 않습니다")
    ready = read_json(paths["ready"])
    if not ready:
        raise SessionError("Jupyter ready 상태가 없습니다")
    node = ready.get("node")
    remote_port = ready.get("port")
    gpu_index = ready.get("gpu_index")
    if not isinstance(node, str) or not NODE_RE.fullmatch(node):
        raise SessionError("Slurm이 배정한 계산 노드를 안전하게 확인할 수 없습니다")
    if type(gpu_index) is not int or not 0 <= gpu_index <= 3 or remote_port != 18880 + gpu_index:
        raise SessionError("Slurm이 배정한 GPU 번호와 Jupyter 포트를 확인할 수 없습니다")
    login_host = config["KSC_LOGIN_HOST"]
    if not LOGIN_HOST_RE.fullmatch(login_host):
        raise SessionError("운영자가 설치한 로그인 호스트 설정이 올바르지 않습니다")
    tunnel_command = shlex.join(
        [
            "ssh",
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "PermitLocalCommand=yes",
            "-o",
            (
                "LocalCommand=echo KSC2026 터널에 정상 접속되었습니다. "
                "이 창을 닫지 말고 브라우저 주소를 여세요."
            ),
            "-L",
            f"127.0.0.1:{LOCAL_JUPYTER_PORT}:{node}:{remote_port}",
            f"{username}@{login_host}",
        ]
    )
    url = (
        f"http://127.0.0.1:{LOCAL_JUPYTER_PORT}/lab/tree/{COURSE_LANDING}"
        f"?token={urllib.parse.quote(token, safe='')}"
    )

    print()
    print("=" * 60)
    print("KSC 2026 JupyterLab 준비 완료")
    print("=" * 60)
    print()
    print("[현재 세션]")
    print(f"로그인 계정 : {username}")
    print(f"Slurm Job ID: {metadata.get('job_id', '') if metadata else ''}")
    print(f"계산 노드   : {node}")
    print(f"배정 GPU    : NVIDIA GH200 120GB · 물리 GPU {gpu_index}번 · 1개")
    print("노트북 표시 : cuda:0 (배정된 GPU 한 개만 보입니다.)")
    print()
    print("[1/2] 로컬 컴퓨터에서 새 터미널 탭을 열어 아래 한 줄을 통째로 붙여 넣으세요.")
    print(tunnel_command)
    print()
    print("OTP와 비밀번호를 입력하면 'KSC2026 터널에 정상 접속되었습니다.'가 표시됩니다.")
    print("메시지가 표시된 뒤에는 터널을 유지하므로 프롬프트가 돌아오지 않습니다. 이 창은 실습 중 열어 두세요.")
    print("'Address already in use'가 나오면 로컬 8888을 쓰는 기존 Jupyter·SSH 터널을 닫고 다시 실행하세요.")
    print()
    print("[2/2] 웹 브라우저에서 아래 주소를 여세요.")
    print(url)
    print()
    print("[저장·재접속]")
    print("- 노트북은 60초마다 자동 저장됩니다. Windows·Linux에서는 Ctrl+S, macOS에서는 Cmd+S를 누르세요.")
    print(f"- 파일 저장 위치: {metadata.get('workspace', '') if metadata else ''}")
    print("- 브라우저나 터널이 끊겨도 Job과 저장 파일은 남습니다.")
    print(f"- PILOT에 다시 로그인해 {SHARED_COMMAND}을 실행하면 기존 세션의 연결 정보를 다시 보여 줍니다.")
    print("- Job이 끝나면 실행 중이던 셀은 중단되고 Python 변수와 GPU 메모리는 사라집니다.")
    print("- 위 브라우저 주소에는 개인 접속 토큰이 포함되어 있으므로 공유하지 마세요.")
    print()
    print("[필요할 때 사용하는 명령]")
    print(f"{SHARED_COMMAND}                  시작 또는 재접속")
    print(f"{SHARED_COMMAND} --refresh       최신 강의자료를 새 작업공간에 준비")
    print(f"{SHARED_COMMAND} --stop           현재 Job 종료 (저장 파일은 유지)")

def runtime_context() -> tuple[Path, dict[str, str], str, dict[str, Path]]:
    if os.environ.get("KSC_SITE_CONFIG"):
        raise SessionError("사이트 설정은 운영자가 설치한 고정 위치만 사용합니다")
    cfg_path = DEFAULT_SITE_CONFIG
    config = parse_site_config(cfg_path)
    username = current_username()
    paths = state_paths(config, cfg_path, username)
    return cfg_path, config, username, paths


def preflight(
    cfg_path: Path, config: dict[str, str], username: str, paths: dict[str, Path]
) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    for name in ("sbatch", "squeue", "scancel", "sinfo"):
        checks.append((f"command:{name}", shutil.which(name) is not None, shutil.which(name) or "없음"))
    try:
        scratch_stat = validate_private_storage(paths)
        checks.append(
            (
                "personal-storage",
                True,
                f"canonical uid={scratch_stat.st_uid} "
                f"mode={stat.S_IMODE(scratch_stat.st_mode):04o}; private descendants uid=current mode=0700",
            )
        )
    except SessionError as exc:
        checks.append(("personal-storage", False, str(exc)))
    try:
        course = read_course(config, cfg_path, username)
        checks.append(("course", True, f"{course.commit[:12]} / {course.source}"))
    except SessionError as exc:
        checks.append(("course", False, str(exc)))
    image = resolve_config_path(config["KSC_IMAGE"], cfg_path, username)
    checks.append(("offline-image", image.is_file() and os.access(image, os.R_OK), str(image)))
    apptainer = resolve_config_path(config["KSC_APPTAINER"], cfg_path, username)
    checks.append(("apptainer", apptainer.is_file() and os.access(apptainer, os.X_OK), str(apptainer)))
    job_script = resolve_config_path(config["KSC_JOB_SCRIPT"], cfg_path, username)
    checks.append(("job-script", job_script.is_file() and os.access(job_script, os.R_OK), str(job_script)))
    partition = config.get("KSC_PARTITION", "gpu")
    process = run(["sinfo", "--noheader", f"--partition={partition}", "--format=%P"], check=False)
    checks.append(("partition", process.returncode == 0 and bool(process.stdout.strip()), partition))
    login_host = config.get("KSC_LOGIN_HOST", "")
    checks.append(("login-host", LOGIN_HOST_RE.fullmatch(login_host) is not None, login_host or "없음"))
    checks.append(("allocation", True, f"account={username}; scheduler-selected node; GH200=1"))
    return checks


def archive_stale(paths: dict[str, Path], metadata: dict[str, object]) -> None:
    ensure_private_dir(paths["archive"], paths["personal_root"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = paths["archive"] / f"metadata-{stamp}-{os.getpid()}.json"
    redacted = dict(metadata)
    redacted.pop("token", None)
    atomic_json(target, redacted)
    for path in (paths["metadata"], paths["ready"], paths["token"]):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def cmd_start(_: argparse.Namespace) -> int:
    cfg_path, config, username, paths = runtime_context()
    failures = [(name, detail) for name, ok, detail in preflight(cfg_path, config, username, paths) if not ok]
    if failures:
        raise SessionError("사전점검 실패\n" + "\n".join(f"- {name}: {detail}" for name, detail in failures))
    ensure_private_dir(paths["state"], paths["personal_root"])
    ensure_private_dir(paths["workspaces"], paths["personal_root"])
    ensure_private_dir(paths["logs"], paths["personal_root"])
    timeout_raw = config.get("KSC_READY_TIMEOUT", "900")
    if not timeout_raw.isdigit() or int(timeout_raw) < 1:
        raise SessionError("KSC_READY_TIMEOUT이 올바르지 않습니다")
    with session_lock(paths["lock"], paths["personal_root"]):
        metadata = read_json(paths["metadata"])
        require_named_job_consistency(metadata, query_named_jobs(username))
        state, _ = session_status(metadata, username, paths)
        if metadata and state in ACTIVE_STATES | {"READY", "STARTING"}:
            workspace = Path(str(metadata.get("workspace", "")))
            require_under(workspace, paths["workspaces"], "기존 작업공간")
            if not validate_private_dir(workspace, paths["personal_root"]):
                raise SessionError("기존 Job의 작업공간이 없습니다")
            workspace_marker = read_json(workspace / ".ksc2026-workspace.json")
            if not workspace_marker or workspace_marker.get("commit") != metadata.get("course_commit"):
                raise SessionError("기존 Job의 작업공간 출처가 저장된 강의 commit과 다릅니다")
            print("기존 JupyterLab 세션에 다시 연결합니다. 잠시 기다려 주세요.")
        else:
            if metadata:
                archive_stale(paths, metadata)
            course = read_course(config, cfg_path, username)
            workspace = select_workspace(course, paths)
            command = build_sbatch(config, cfg_path, username, paths, workspace, course)
            process = run(command, cwd=Path("/scratch") / username)
            job_id = process.stdout.strip().split(";", 1)[0]
            if not JOB_RE.fullmatch(job_id):
                raise SessionError(f"sbatch가 올바른 Job ID를 반환하지 않았습니다: {process.stdout!r}")
            metadata = {
                "schema_version": 2,
                "account": username,
                "gpu_count": 1,
                "job_id": job_id,
                "workspace": str(workspace),
                "course_commit": course.commit,
                "sif_sha256": course.sif_sha256,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            atomic_json(paths["metadata"], metadata)
            print("JupyterLab을 준비합니다. 잠시 기다려 주세요.")
    assert metadata is not None
    state = wait_ready(metadata, username, paths, int(timeout_raw))
    emit_session(state, config, username, metadata, paths)
    return 0


def prepare_course_copy() -> int:
    cfg_path, config, username, paths = runtime_context()
    validate_private_storage(paths)
    ensure_private_dir(paths["state"], paths["personal_root"])
    ensure_private_dir(paths["workspaces"], paths["personal_root"])
    with session_lock(paths["lock"], paths["personal_root"]):
        metadata = read_json(paths["metadata"])
        require_named_job_consistency(metadata, query_named_jobs(username))
        state, _ = session_status(metadata, username, paths)
        if metadata and state in ACTIVE_STATES | {"READY", "STARTING"}:
            raise SessionError("실행 중인 세션이 있습니다. 먼저 --stop을 실행하세요")
        if metadata:
            archive_stale(paths, metadata)
        course = read_course(config, cfg_path, username)
        workspace = prepare_workspace(course, paths)
        previous = read_json(paths["active_workspace"])
        set_active_workspace(course, workspace, paths)
    print(f"운영자가 게시한 최신 강의자료 작업공간을 준비했습니다: {workspace}")
    if previous and previous.get("workspace") != str(workspace):
        print(f"이전 작업공간은 삭제하지 않았습니다: {previous.get('workspace', '')}")
    return 0


def cmd_refresh(_: argparse.Namespace) -> int:
    return prepare_course_copy()


def cmd_stop(_: argparse.Namespace) -> int:
    _, config, username, paths = runtime_context()
    validate_private_storage(paths)
    ensure_private_dir(paths["state"], paths["personal_root"])
    with session_lock(paths["lock"], paths["personal_root"]):
        metadata = read_json(paths["metadata"])
        require_named_job_consistency(metadata, query_named_jobs(username))
        if not metadata:
            emit_session("ABSENT", config, username, None, paths)
            return 0
        if (
            metadata.get("schema_version") != 2
            or metadata.get("account") != username
            or metadata.get("gpu_count") != 1
        ):
            raise SessionError("저장된 세션 정보가 현재 공용 1-GPU 형식과 다릅니다")
        job_id = str(metadata.get("job_id", ""))
        job = query_job(job_id) if JOB_RE.fullmatch(job_id) else None
        if job:
            if job["owner"] != username or job["name"] != f"ksc26-jlab-{username}":
                raise SessionError("현재 계정의 KSC2026 Job으로 확인되지 않아 종료하지 않습니다")
            run(["scancel", job_id])
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and query_job(job_id):
                time.sleep(1)
            if query_job(job_id):
                raise SessionError("60초 안에 Job 종료를 확인하지 못했습니다")
        archive_stale(paths, metadata)
    print("세션을 종료했습니다. 작업공간과 로그는 삭제하지 않았습니다.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, function in (
        ("start", cmd_start),
        ("refresh", cmd_refresh),
        ("stop", cmd_stop),
    ):
        child = subparsers.add_parser(command)
        child.set_defaults(func=function)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SessionError as exc:
        print(f"KSC2026 오류: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
