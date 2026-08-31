#!/usr/bin/env python3
"""Regression guards for the map-free, role-free shared runtime."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader(
    "unified_session_controller", str(ROOT / "session-controller.py")
)
SPEC = importlib.util.spec_from_loader("unified_session_controller", LOADER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class UnifiedRuntimeContractTests(unittest.TestCase):
    def active_text(self) -> str:
        return "\n".join(
            (ROOT / name).read_text(encoding="utf-8")
            for name in ("ksc2026", "start-jupyter", "session-controller.py", "jupyter-job.sh")
        )

    def test_legacy_roster_artifacts_are_not_runtime_inputs(self) -> None:
        for name in ("account_map.py", "account-map-contract.json"):
            self.assertFalse((ROOT / name).exists(), f"legacy runtime roster remains: {name}")

    def test_current_identity_comes_from_id_un_not_user_environment(self) -> None:
        completed = mock.Mock(returncode=0, stdout="edu042\n", stderr="")
        with mock.patch.dict("os.environ", {"USER": "spoofed"}), mock.patch.object(
            MODULE.subprocess, "run", return_value=completed
        ) as runner:
            self.assertEqual(MODULE.current_username(), "edu042")
        runner.assert_called_once_with(
            ["id", "-un"],
            text=True,
            stdout=MODULE.subprocess.PIPE,
            stderr=MODULE.subprocess.PIPE,
            check=False,
        )

    def test_active_runtime_has_no_role_roster_or_protected_node_route(self) -> None:
        text = self.active_text()
        for forbidden in (
            "account-map",
            "account_map",
            "instructor-route",
            "KSC_STUDENT_RESERVATION",
            "KSC_INSTRUCTOR",
            "--nodelist",
            "--exclude",
        ):
            self.assertNotIn(forbidden, text)

    def test_site_configuration_supplies_login_host_not_a_node_roster(self) -> None:
        text = (ROOT / "site.env.example").read_text(encoding="utf-8")
        self.assertIn("KSC_LOGIN_HOST=REPLACE_WITH_EVENT_LOGIN_HOST", text)
        for forbidden in (
            "ACCOUNT_MAP",
            "INSTRUCTOR",
            "STUDENT",
            "NODELIST",
            "EXCLUDE",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
