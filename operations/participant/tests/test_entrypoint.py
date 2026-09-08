#!/usr/bin/env python3
"""Tests for the one role-free KSC 2026 user entry point."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "start-jupyter"


class UnifiedEntrypointTests(unittest.TestCase):
    def run_with_fake_runtime(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="ksc2026-unified-entry-") as temporary:
            fake_bin = Path(temporary)
            module = fake_bin / "module"
            module.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            module.chmod(0o755)
            python = fake_bin / "python3"
            python.write_text(
                "#!/usr/bin/env bash\nprintf 'PYTHON_ARGS='\nprintf '%s ' \"$@\"\nprintf '\\n'\n",
                encoding="utf-8",
            )
            python.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:{environment.get('PATH', '')}"
            return subprocess.run(
                [str(ENTRYPOINT), *arguments],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                check=False,
            )

    def test_default_command_dispatches_start(self) -> None:
        result = self.run_with_fake_runtime()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"session-controller\.py start\s*$")

    def test_public_refresh_and_stop_options_map_to_controller_commands(self) -> None:
        refresh = self.run_with_fake_runtime("--refresh")
        self.assertEqual(refresh.returncode, 0, refresh.stderr)
        self.assertRegex(refresh.stdout, r"session-controller\.py refresh\s*$")

        stop = self.run_with_fake_runtime("--stop")
        self.assertEqual(stop.returncode, 0, stop.stderr)
        self.assertRegex(stop.stdout, r"session-controller\.py stop\s*$")

    def test_help_exposes_only_three_normal_user_commands(self) -> None:
        result = subprocess.run(
            [str(ENTRYPOINT), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        text = result.stdout + result.stderr
        self.assertIn("ksc2026              Jupyter", text)
        self.assertIn("ksc2026 --refresh", text)
        self.assertIn("ksc2026 --stop", text)
        for hidden in ("--status", "--preflight", "--fresh-course", "--refresh-course"):
            self.assertNotIn(hidden, text)

    def test_entrypoint_has_no_role_or_fixed_node_route(self) -> None:
        text = ENTRYPOINT.read_text(encoding="utf-8")
        for forbidden in (
            "instructor-route",
            "route_instructor",
            "account-map",
            "account_map",
            "--nodelist",
            "--exclude",
        ):
            self.assertNotIn(forbidden, text)
        self.assertNotRegex(text, r"\bgpu[0-9]{4}\b")


if __name__ == "__main__":
    unittest.main()
