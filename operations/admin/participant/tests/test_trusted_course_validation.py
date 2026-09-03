#!/usr/bin/env python3
"""Prove that course publication never executes validators from fetched Git."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parents[3]
TRUSTED_COURSE_VALIDATOR = ROOT / "tools/validate_course.py"
TRUSTED_PARTICIPANT_VALIDATOR = ROOT / "tools/validate_participant_release.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ksc2026-untrusted-course-") as temporary:
        temporary_root = Path(temporary)
        target = temporary_root / "fetched"
        sentinel = temporary_root / "UNTRUSTED_CODE_EXECUTED"
        shutil.copytree(
            ROOT,
            target,
            symlinks=True,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )

        malicious_python = (
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('python executed', encoding='utf-8')\n"
            "print('KSC2026_PARTICIPANT_RELEASE_VALID=1')\n"
        )
        for relative in (
            "tools/validate_course.py",
            "tools/validate_participant_release.py",
        ):
            path = target / relative
            path.write_text(malicious_python, encoding="utf-8")
            path.chmod(0o755)

        malicious_shell = (
            "#!/usr/bin/env bash\n"
            f"printf shell-executed > {str(sentinel)!r}\n"
        )
        for relative in (
            "operations/participant/tests/run-session-tests.sh",
            "operations/admin/participant/tests/run-tests.sh",
        ):
            path = target / relative
            path.write_text(malicious_shell, encoding="utf-8")
            path.chmod(0o755)

        environment = os.environ.copy()
        environment["GITHUB_ACTIONS"] = "true"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                str(TRUSTED_COURSE_VALIDATOR),
                "--root",
                str(target),
                "--participant-validator",
                str(TRUSTED_PARTICIPANT_VALIDATOR),
                "--static-only",
            ],
            cwd=str(ROOT),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
            check=False,
        )
        require(result.returncode == 0, f"trusted validation failed:\n{result.stdout}")
        require(
            "participant release passes the canonical payload validator" in result.stdout,
            "trusted participant validator success marker is absent",
        )
        require(not sentinel.exists(), "a validator or test from fetched Git was executed")

    print("PASS: fetched validators and operation suites are never executed")


if __name__ == "__main__":
    main()
