#!/usr/bin/env python3
"""Exercise the stable participant wrapper's deployment-lock contract."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import textwrap
import time


TEST_DIR = Path(__file__).resolve().parent
OPERATIONS_DIR = TEST_DIR.parents[2]
WRAPPER_SOURCE = OPERATIONS_DIR / "participant" / "ksc2026"
INSTALLER = TEST_DIR.parent / "install-participants.sh"
PUBLISHER = TEST_DIR.parents[1] / "publish-course.sh"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def wait_for(path: Path, process: subprocess.Popen[str], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                "wrapper exited before attempting its shared lock: "
                f"rc={process.returncode} stdout={stdout!r} stderr={stderr!r}"
            )
        time.sleep(0.01)
    raise AssertionError("wrapper did not attempt its shared lock before timeout")


def assert_source_contract() -> None:
    wrapper = WRAPPER_SOURCE.read_text(encoding="utf-8")
    installer = INSTALLER.read_text(encoding="utf-8")
    publisher = PUBLISHER.read_text(encoding="utf-8")

    for marker in (
        '"$(stat -c \'%u:%a:%h\' "$deployment_lock")" == "$central_uid:644:1"',
        'exec 9<"$deployment_lock"',
        "flock -s 9",
        "stat -Lc '%d:%i' /dev/fd/9",
        "without close-on-exec",
    ):
        require(marker in wrapper, f"wrapper lock contract marker missing: {marker}")

    for marker in (
        '"$central_uid:644:1"',
        "flock -x -n 9",
        "CENTRAL_ENTRYPOINT_IMMUTABLE_CONTENT_MISMATCH",
        'if [[ "$entrypoint_action" == INSTALL ]]',
        'entrypoint_target="$central_root/bin/ksc2026"',
    ):
        require(marker in installer, f"installer atomic-runtime marker missing: {marker}")

    for marker in (
        '"$actor_uid:644:1"',
        "( umask 022; set -o noclobber; : >\"$deployment_lock\" )",
        "flock -x -n 9",
    ):
        require(marker in publisher, f"publisher lock marker missing: {marker}")


def main() -> None:
    assert_source_contract()

    with tempfile.TemporaryDirectory(prefix="ksc2026-runtime-lock-") as temp_value:
        root = Path(temp_value) / "ksc2026"
        bin_dir = root / "bin"
        admin_dir = root / "admin"
        tool_dir = Path(temp_value) / "tools"
        for directory in (bin_dir, admin_dir, tool_dir):
            directory.mkdir(parents=True, mode=0o755)

        wrapper = bin_dir / "ksc2026"
        shutil.copyfile(WRAPPER_SOURCE, wrapper)
        wrapper.chmod(0o755)

        deployment_lock = admin_dir / "deployment.lock"
        deployment_lock.touch(mode=0o644)
        deployment_lock.chmod(0o644)
        trace = Path(temp_value) / "shared-lock-attempted"

        write_executable(
            tool_dir / "flock",
            r"""
            #!/usr/bin/env python3
            import fcntl
            import os
            import sys

            arguments = sys.argv[1:]
            operation = fcntl.LOCK_EX
            nonblocking = False
            unlock = False
            descriptor_text = None
            for argument in arguments:
                if argument in ("-s", "--shared"):
                    operation = fcntl.LOCK_SH
                elif argument in ("-x", "--exclusive"):
                    operation = fcntl.LOCK_EX
                elif argument in ("-n", "--nonblock"):
                    nonblocking = True
                elif argument in ("-u", "--unlock"):
                    unlock = True
                elif not argument.startswith("-"):
                    descriptor_text = argument
            if descriptor_text is None:
                raise SystemExit(2)
            descriptor = int(descriptor_text)
            if unlock:
                operation = fcntl.LOCK_UN
            elif nonblocking:
                operation |= fcntl.LOCK_NB
            trace_path = os.environ.get("KSC_TEST_SHARED_LOCK_TRACE")
            if trace_path and operation & fcntl.LOCK_SH and not operation & fcntl.LOCK_UN:
                with open(trace_path, "w", encoding="utf-8") as stream:
                    stream.write("SHARED_LOCK_ATTEMPTED\n")
            try:
                fcntl.flock(descriptor, operation)
            except BlockingIOError:
                raise SystemExit(1)
            """,
        )
        write_executable(
            tool_dir / "stat",
            r"""
            #!/usr/bin/env python3
            import os
            import stat
            import sys

            arguments = sys.argv[1:]
            if len(arguments) != 3 or arguments[0] not in ("-c", "-Lc"):
                raise SystemExit(2)
            format_value, path = arguments[1], arguments[2]
            if path.startswith("/dev/fd/"):
                value = os.fstat(int(path.rsplit("/", 1)[1]))
            else:
                value = os.stat(path)
            replacements = {
                "%u": str(value.st_uid),
                "%a": format(stat.S_IMODE(value.st_mode), "o"),
                "%h": str(value.st_nlink),
                "%d": str(value.st_dev),
                "%i": str(value.st_ino),
            }
            for key, replacement in replacements.items():
                format_value = format_value.replace(key, replacement)
            trace_path = os.environ.get("KSC_TEST_STAT_TRACE")
            if trace_path:
                with open(trace_path, "a", encoding="utf-8") as stream:
                    stream.write(f"{arguments!r} -> {format_value!r}\n")
            print(format_value)
            """,
        )
        write_executable(
            bin_dir / "start-jupyter",
            r"""
            #!/usr/bin/env bash
            set -Eeuo pipefail
            script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
            central_root="${script_dir%/bin}"
            exec /usr/bin/env -u PYTHONPATH -u PYTHONHOME python3 -B \
                "$script_dir/controller-probe.py" \
                "$central_root/admin/deployment.lock"
            """,
        )
        write_executable(
            bin_dir / "controller-probe.py",
            r"""
            #!/usr/bin/env python3
            import fcntl
            import os
            import sys

            try:
                os.fstat(9)
            except OSError as error:
                raise SystemExit(f"shared lock FD 9 did not survive controller exec: {error}")
            probe = os.open(sys.argv[1], os.O_RDWR)
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("RUNTIME_LOCK_HELD_ACROSS_EXEC=1")
            else:
                raise SystemExit("shared lock was not held across controller exec")
            finally:
                os.close(probe)
            """,
        )

        environment = os.environ.copy()
        environment["PATH"] = f"{tool_dir}{os.pathsep}{environment.get('PATH', '')}"
        environment["KSC_TEST_SHARED_LOCK_TRACE"] = str(trace)
        stat_trace = Path(temp_value) / "stat-trace"
        environment["KSC_TEST_STAT_TRACE"] = str(stat_trace)

        lock_descriptor = os.open(deployment_lock, os.O_RDWR)
        process: subprocess.Popen[str] | None = None
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            process = subprocess.Popen(
                [str(wrapper)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
            wait_for(trace, process)
            require(process.poll() is None, "wrapper did not block behind exclusive lock")
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            stdout, stderr = process.communicate(timeout=5)
            require(
                process.returncode == 0,
                f"wrapper failed: {stderr}; stat trace={stat_trace.read_text()!r}",
            )
            require(
                stdout == "RUNTIME_LOCK_HELD_ACROSS_EXEC=1\n",
                f"unexpected wrapper output: {stdout!r}",
            )
        finally:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            os.close(lock_descriptor)
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)

        deployment_lock.chmod(0o664)
        bad_mode = subprocess.run(
            [str(wrapper)], capture_output=True, text=True, env=environment, timeout=5
        )
        require(bad_mode.returncode != 0, "wrapper accepted a group-writable lock")
        require("owner, mode" in bad_mode.stderr, "bad lock mode was not identified")
        deployment_lock.chmod(0o644)

        hardlink = admin_dir / "deployment.hardlink"
        os.link(deployment_lock, hardlink)
        linked = subprocess.run(
            [str(wrapper)], capture_output=True, text=True, env=environment, timeout=5
        )
        require(linked.returncode != 0, "wrapper accepted a multiply-linked lock")
        hardlink.unlink()

        real_lock = admin_dir / "deployment.real"
        deployment_lock.rename(real_lock)
        deployment_lock.symlink_to(real_lock.name)
        symlinked = subprocess.run(
            [str(wrapper)], capture_output=True, text=True, env=environment, timeout=5
        )
        require(symlinked.returncode != 0, "wrapper accepted a symlink lock")

    print("PASS: shared wrapper lock blocks, survives exec, and rejects unsafe metadata")


if __name__ == "__main__":
    main()
