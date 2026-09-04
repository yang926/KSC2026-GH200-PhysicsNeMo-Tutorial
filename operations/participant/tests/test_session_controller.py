from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOADER = importlib.machinery.SourceFileLoader(
    "participant_session_controller", str(ROOT / "session-controller.py")
)
SPEC = importlib.util.spec_from_loader("participant_session_controller", LOADER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class UnifiedSessionControllerTests(unittest.TestCase):
    def personal_root(self, base: Path, *, mode: int = 0o755) -> Path:
        scratch = base / "scratch"
        scratch.mkdir(mode=0o755)
        personal = scratch / "edu001"
        personal.mkdir(mode=mode)
        os.chmod(personal, mode)
        return personal

    def paths(self, personal: Path) -> dict[str, Path]:
        state = personal / "ksc2026" / "session"
        workspaces = personal / "ksc2026" / "workspaces"
        logs = personal / "ksc2026" / "logs"
        return {
            "personal_root": personal,
            "account_root": personal / "ksc2026",
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

    def course(self, root: Path):
        return MODULE.Course(
            source=root / "course",
            commit="a" * 40,
            runtime_compatibility="runtime-v1",
            sif_sha256="b" * 64,
        )

    def active_metadata(self, workspace: Path) -> dict[str, object]:
        return {
            "schema_version": 2,
            "account": "edu001",
            "gpu_count": 1,
            "job_id": "314",
            "workspace": str(workspace),
            "course_commit": "a" * 40,
            "sif_sha256": "b" * 64,
        }

    def write_ready(
        self,
        paths: dict[str, Path],
        *,
        node: str,
        gpu_index: int,
        course_commit: str = "a" * 40,
    ) -> None:
        paths["state"].mkdir(parents=True, exist_ok=True)
        os.chmod(paths["state"], 0o700)
        paths["token"].write_text("c" * 48 + "\n", encoding="ascii")
        os.chmod(paths["token"], 0o600)
        paths["ready"].write_text(
            json.dumps(
                {
                    "job_id": "314",
                    "node": node,
                    "port": 18880 + gpu_index,
                    "gpu_index": gpu_index,
                    "course_commit": course_commit,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(paths["ready"], 0o600)

    def read_control_leaf(self, name: str, path: Path):
        if name == "token":
            return MODULE.read_private_text(path, "Jupyter token", encoding="ascii")
        return MODULE.read_json(path)

    def control_content(self, name: str) -> str:
        if name == "token":
            return "c" * 48 + "\n"
        return '{"schema_version": 2}\n'

    def test_sbatch_requests_one_gpu_and_leaves_node_selection_to_slurm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "site.env"
            config_path.write_text("", encoding="utf-8")
            paths = {"state": root / "state", "logs": root / "logs"}
            workspace = Path("/scratch/edu001/ksc2026/workspaces/course-aaaaaaaaaaaa")
            config = {
                "KSC_IMAGE": "/scratch/hackathon/ksc2026/images/course.sif",
                "KSC_APPTAINER": "/apps/common/apptainer/1.4.5/aarch64/bin/apptainer",
                "KSC_JOB_SCRIPT": "/scratch/hackathon/ksc2026/slurm/jupyter-job.sh",
                "KSC_PARTITION": "gpu",
                "KSC_TIME_LIMIT": "1-00:00:00",
            }
            command = MODULE.build_sbatch(
                config, config_path, "edu001", paths, workspace, self.course(root)
            )

        self.assertIn("--partition=gpu", command)
        self.assertIn("--nodes=1", command)
        self.assertIn("--ntasks=1", command)
        self.assertIn("--gres=gpu:nvidia_gh200_120gb:1", command)
        self.assertIn("--time=1-00:00:00", command)
        self.assertIn("--chdir=/scratch/edu001", command)
        for forbidden in (
            "--nodelist=",
            "--exclude=",
            "--reservation=",
            "--exclusive",
            "CUDA_VISIBLE_DEVICES",
            "KSC_EXPECTED_NODE",
            "KSC_REMOTE_PORT",
        ):
            self.assertFalse(
                any(forbidden in argument for argument in command),
                f"scheduler constraint remains: {forbidden}",
            )
        exported = next(value for value in command if value.startswith("--export="))
        self.assertIn("KSC_EXPECTED_GPU_COUNT=1", exported)
        self.assertIn("KSC_ENTRY_NOTEBOOK=00_Start_Here.ipynb", exported)
        self.assertIn("KSC_LANDING_PAGE=README.md", exported)
        self.assertIn("KSC_LOG_DIR=", exported)
        self.assertNotIn("--export=ALL", exported)

    def test_state_paths_are_the_same_for_every_authenticated_account(self) -> None:
        paths = MODULE.state_paths({}, Path("/apps/ksc2026/config/site.env"), "edu001")
        self.assertEqual(paths["personal_root"], Path("/scratch/edu001"))
        self.assertEqual(paths["state"], Path("/scratch/edu001/ksc2026/session"))
        self.assertEqual(paths["workspaces"], Path("/scratch/edu001/ksc2026/workspaces"))
        self.assertEqual(paths["logs"], Path("/scratch/edu001/ksc2026/logs"))

    def test_preflight_reports_scheduler_selected_one_gpu_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            personal = self.personal_root(base)
            paths = self.paths(personal)
            image = base / "course.sif"
            image.write_text("image", encoding="utf-8")
            apptainer = base / "apptainer"
            apptainer.write_text("binary", encoding="utf-8")
            os.chmod(apptainer, 0o700)
            job_script = base / "jupyter-job.sh"
            job_script.write_text("#!/bin/bash\n", encoding="utf-8")
            config = {
                "KSC_IMAGE": str(image),
                "KSC_APPTAINER": str(apptainer),
                "KSC_JOB_SCRIPT": str(job_script),
                "KSC_PARTITION": "gpu",
                "KSC_LOGIN_HOST": "pilot.example.test",
            }
            process = subprocess.CompletedProcess([], 0, stdout="gpu\n", stderr="")
            with mock.patch.object(
                MODULE, "validate_private_storage", return_value=personal.stat()
            ), mock.patch.object(
                MODULE, "read_course", return_value=self.course(base)
            ), mock.patch.object(
                MODULE.shutil, "which", return_value="/bin/tool"
            ), mock.patch.object(MODULE, "run", return_value=process):
                checks = MODULE.preflight(base / "site.env", config, "edu001", paths)

        allocation = next(check for check in checks if check[0] == "allocation")
        self.assertTrue(allocation[1])
        self.assertIn("account=edu001", allocation[2])
        self.assertIn("scheduler-selected node", allocation[2])
        self.assertIn("GH200=1", allocation[2])

    def test_ready_uses_actual_slurm_node_gpu_and_derived_port(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            personal = self.personal_root(Path(temporary).resolve())
            paths = self.paths(personal)
            self.write_ready(paths, node="compute018", gpu_index=3)
            metadata = self.active_metadata(
                personal / "ksc2026" / "workspaces" / "course-aaaaaaaaaaaa"
            )
            job = {
                "job_id": "314",
                "owner": "edu001",
                "state": "RUNNING",
                "node": "compute018",
                "name": "ksc26-jlab-edu001",
            }
            with mock.patch.object(MODULE, "query_job", return_value=job), mock.patch.object(
                MODULE, "authenticated_http_ready", return_value=True
            ) as http_ready:
                state, returned_job = MODULE.session_status(metadata, "edu001", paths)

        self.assertEqual(state, "READY")
        self.assertEqual(returned_job, job)
        http_ready.assert_called_once_with("compute018", 18883, "c" * 48)

    def test_ready_rejects_endpoint_that_does_not_match_slurm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            personal = self.personal_root(Path(temporary).resolve())
            paths = self.paths(personal)
            self.write_ready(paths, node="compute017", gpu_index=2)
            metadata = self.active_metadata(
                personal / "ksc2026" / "workspaces" / "course-aaaaaaaaaaaa"
            )
            job = {
                "job_id": "314",
                "owner": "edu001",
                "state": "RUNNING",
                "node": "compute004",
                "name": "ksc26-jlab-edu001",
            }
            with mock.patch.object(MODULE, "query_job", return_value=job), mock.patch.object(
                MODULE, "authenticated_http_ready", return_value=True
            ) as http_ready:
                state, _ = MODULE.session_status(metadata, "edu001", paths)

        self.assertEqual(state, "STARTING")
        http_ready.assert_not_called()

    def test_ready_output_prints_complete_second_tab_tunnel_and_browser_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            personal = self.personal_root(Path(temporary).resolve())
            paths = self.paths(personal)
            self.write_ready(paths, node="compute017", gpu_index=2)
            workspace = personal / "ksc2026" / "workspaces" / "course-aaaaaaaaaaaa"
            metadata = self.active_metadata(workspace)
            output = io.StringIO()
            with redirect_stdout(output):
                MODULE.emit_session(
                    "READY",
                    {"KSC_LOGIN_HOST": "pilot.example.test"},
                    "edu001",
                    metadata,
                    paths,
                )
            text = output.getvalue()

        tunnel = (
            "ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 "
            "-o ServerAliveCountMax=3 -o PermitLocalCommand=yes "
            "-o 'LocalCommand=echo [KSC2026] 정상 접속되었습니다. "
            "이 창을 닫지 말고 브라우저 주소를 여세요.' -L "
            "127.0.0.1:8888:compute017:18882 edu001@pilot.example.test"
        )
        url = (
            "http://127.0.0.1:8888/lab/tree/README.md?token="
            + "c" * 48
        )
        self.assertIn("계산 노드   : compute017", text)
        self.assertIn("물리 GPU 2번 · 1개", text)
        self.assertIn("[1/2] 로컬 컴퓨터에서 새 터미널 탭", text)
        self.assertIn(tunnel, text)
        self.assertIn("OTP와 비밀번호를 입력하면 '[KSC2026] 정상 접속되었습니다.'", text)
        self.assertIn("터널을 유지하므로 프롬프트가 돌아오지 않습니다", text)
        self.assertNotIn("영문 대문자 L", text)
        self.assertNotIn("아무 출력 없이", text)
        self.assertIn("[2/2] 웹 브라우저", text)
        self.assertIn(url, text)
        self.assertIn("Address already in use", text)
        self.assertLess(text.index(tunnel), text.index(url))
        self.assertIn("[필요할 때 사용하는 명령]", text)
        self.assertIn(f"{MODULE.SHARED_COMMAND}                  시작 또는 재접속", text)
        self.assertIn(f"{MODULE.SHARED_COMMAND} --refresh", text)
        self.assertIn(f"{MODULE.SHARED_COMMAND} --stop", text)
        for hidden in ("--status", "--preflight", "--fresh-course", "--refresh-course"):
            self.assertNotIn(hidden, text)
        self.assertNotIn("강사", text)
        self.assertNotIn("교육생", text)

    def test_active_reconnect_submits_zero_new_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            personal = self.personal_root(Path(temporary).resolve())
            paths = self.paths(personal)
            workspace = paths["workspaces"] / "course-aaaaaaaaaaaa"
            metadata = self.active_metadata(workspace)
            job = {
                "job_id": "314",
                "owner": "edu001",
                "state": "RUNNING",
                "node": "compute019",
                "name": "ksc26-jlab-edu001",
            }

            def read_json(path: Path):
                if path == paths["metadata"]:
                    return metadata
                if path == workspace / ".ksc2026-workspace.json":
                    return {"commit": "a" * 40}
                raise AssertionError(f"unexpected JSON read: {path}")

            context = (
                Path("/scratch/hackathon/ksc2026/config/site.env"),
                {"KSC_READY_TIMEOUT": "900", "KSC_LOGIN_HOST": "pilot.example.test"},
                "edu001",
                paths,
            )
            with mock.patch.object(MODULE, "runtime_context", return_value=context), mock.patch.object(
                MODULE, "preflight", return_value=[("all", True, "ok")]
            ), mock.patch.object(MODULE, "ensure_private_dir"), mock.patch.object(
                MODULE, "session_lock", return_value=nullcontext()
            ), mock.patch.object(MODULE, "read_json", side_effect=read_json), mock.patch.object(
                MODULE, "query_named_jobs", return_value=[job]
            ), mock.patch.object(MODULE, "require_named_job_consistency"), mock.patch.object(
                MODULE, "session_status", return_value=("READY", job)
            ), mock.patch.object(MODULE, "require_under"), mock.patch.object(
                MODULE, "validate_private_dir", return_value=True
            ), mock.patch.object(MODULE, "wait_ready", return_value="READY"), mock.patch.object(
                MODULE, "emit_session"
            ) as emit_session, mock.patch.object(MODULE, "run") as command_runner:
                result = MODULE.cmd_start(mock.Mock())

        self.assertEqual(result, 0)
        command_runner.assert_not_called()
        emit_session.assert_called_once_with(
            "READY", context[1], "edu001", metadata, paths
        )

    def test_job_payload_derives_ready_endpoint_from_slurm_allocation(self) -> None:
        script = (ROOT / "jupyter-job.sh").read_text(encoding="utf-8")
        for marker in (
            'compute_node="$(hostname -s)"',
            "slurm_job_gpus=${SLURM_JOB_GPUS:-}",
            '[[ "$slurm_job_gpus" =~ ^[0-3]$ ]]',
            "remote_port=$((18880 + 10#$slurm_job_gpus))",
            '"$SLURM_JOB_ID" "$compute_node" "$remote_port" "$slurm_job_gpus"',
            '"gpu_index":%s',
            '"course_commit":"%s"',
            '"defaultViewers":{"markdown":"Markdown Preview"}',
            "c.ServerApp.default_url = '/lab/tree/$KSC_LANDING_PAGE'",
        ):
            self.assertIn(marker, script)
        for forbidden in (
            "KSC_EXPECTED_NODE",
            "KSC_REMOTE_PORT",
            "--nodelist",
            "--exclude",
            "CUDA_VISIBLE_DEVICES=",
        ):
            self.assertNotIn(forbidden, script)

    def test_lock_is_released_when_a_command_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            personal = self.personal_root(Path(temporary).resolve())
            lock = personal / "ksc2026" / "session" / "lock"
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                with MODULE.session_lock(lock, personal, timeout=0):
                    raise RuntimeError("simulated failure")
            with MODULE.session_lock(lock, personal, timeout=0):
                self.assertTrue(lock.is_file())
                self.assertEqual(lock.stat().st_mode & 0o777, 0o600)

    def test_personal_scratch_accepts_pilot_modes_and_rejects_writable_mode(self) -> None:
        for permissions in (0o700, 0o750, 0o755):
            with self.subTest(mode=f"{permissions:04o}"), tempfile.TemporaryDirectory() as temporary:
                personal = self.personal_root(Path(temporary).resolve(), mode=permissions)
                result = MODULE.validate_personal_scratch(personal)
                self.assertEqual(result.st_uid, os.getuid())
                self.assertEqual(result.st_mode & 0o777, permissions)

        with tempfile.TemporaryDirectory() as temporary:
            personal = self.personal_root(Path(temporary).resolve(), mode=0o770)
            with self.assertRaisesRegex(MODULE.SessionError, "쓰기"):
                MODULE.validate_personal_scratch(personal)

    def test_personal_scratch_rejects_wrong_owner_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            personal = self.personal_root(base)
            with mock.patch.object(MODULE.os, "getuid", return_value=os.getuid() + 1):
                with self.assertRaisesRegex(MODULE.SessionError, "현재 계정 소유"):
                    MODULE.validate_personal_scratch(personal)

            linked = base / "linked-personal"
            linked.symlink_to(personal, target_is_directory=True)
            with self.assertRaisesRegex(MODULE.SessionError, "심볼릭 링크 없이"):
                MODULE.validate_personal_scratch(linked)

    def test_private_directory_creation_is_0700_and_rejects_symlink_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            personal = self.personal_root(base)
            paths = self.paths(personal)
            MODULE.ensure_private_dir(paths["logs"], personal)
            self.assertEqual((personal / "ksc2026").stat().st_mode & 0o777, 0o700)
            self.assertEqual(paths["logs"].stat().st_mode & 0o777, 0o700)

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            personal = self.personal_root(base)
            outside = base / "outside"
            outside.mkdir(mode=0o700)
            (personal / "ksc2026").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(MODULE.SessionError, "실제 디렉터리가 아닌"):
                MODULE.ensure_private_dir(personal / "ksc2026" / "session", personal)

    def test_control_leaves_reject_symlinks(self) -> None:
        for name in ("metadata", "ready", "token"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary).resolve()
                personal = self.personal_root(base)
                paths = self.paths(personal)
                MODULE.ensure_private_dir(paths["state"], personal)
                outside = base / f"outside-{name}"
                outside.write_text(self.control_content(name), encoding="ascii")
                os.chmod(outside, 0o600)
                paths[name].symlink_to(outside)
                with self.assertRaises(MODULE.SessionError):
                    self.read_control_leaf(name, paths[name])

    def test_control_leaves_reject_hardlinks(self) -> None:
        for name in ("metadata", "ready", "token"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary).resolve()
                personal = self.personal_root(base)
                paths = self.paths(personal)
                MODULE.ensure_private_dir(paths["state"], personal)
                outside = base / f"outside-{name}"
                outside.write_text(self.control_content(name), encoding="ascii")
                os.chmod(outside, 0o600)
                os.link(outside, paths[name])
                with self.assertRaisesRegex(MODULE.SessionError, "nlink 1"):
                    self.read_control_leaf(name, paths[name])

    def test_control_leaves_reject_fifos_without_blocking(self) -> None:
        for name in ("metadata", "ready", "token"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                personal = self.personal_root(Path(temporary).resolve())
                paths = self.paths(personal)
                MODULE.ensure_private_dir(paths["state"], personal)
                os.mkfifo(paths[name], 0o600)
                with self.assertRaisesRegex(MODULE.SessionError, "일반 파일"):
                    self.read_control_leaf(name, paths[name])

    def test_orphan_and_duplicate_managed_jobs_fail_closed(self) -> None:
        job = {
            "job_id": "314",
            "owner": "edu001",
            "state": "RUNNING",
            "node": "compute007",
            "name": "ksc26-jlab-edu001",
        }
        with self.assertRaisesRegex(MODULE.SessionError, "상태 파일 없이"):
            MODULE.require_named_job_consistency(None, [job])

        metadata = {"job_id": "314"}
        MODULE.require_named_job_consistency(metadata, [job])
        duplicate = dict(job, job_id="315")
        with self.assertRaisesRegex(MODULE.SessionError, "저장 Job과 실제"):
            MODULE.require_named_job_consistency(metadata, [job, duplicate])

    def test_ready_requires_token_authenticated_http_response(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            personal = self.personal_root(Path(temporary).resolve())
            paths = self.paths(personal)
            self.write_ready(paths, node="compute007", gpu_index=1)
            metadata = self.active_metadata(paths["workspaces"] / "course-aaaaaaaaaaaa")
            job = {
                "job_id": "314",
                "owner": "edu001",
                "state": "RUNNING",
                "node": "compute007",
                "name": "ksc26-jlab-edu001",
            }
            with mock.patch.object(MODULE, "query_job", return_value=job), mock.patch.object(
                MODULE, "authenticated_http_ready", return_value=False
            ) as http_ready:
                state, _ = MODULE.session_status(metadata, "edu001", paths)

        self.assertEqual(state, "STARTING")
        http_ready.assert_called_once_with("compute007", 18881, "c" * 48)
        self.assertFalse(MODULE.authenticated_http_ready("compute007", 18881, "short-token"))

    def test_ready_rejects_invalid_gpu_index_and_port(self) -> None:
        cases = (
            {"gpu_index": 4, "port": 18884},
            {"gpu_index": 2, "port": 18883},
            {"gpu_index": 2, "port": "18882"},
        )
        for replacement in cases:
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as temporary:
                personal = self.personal_root(Path(temporary).resolve())
                paths = self.paths(personal)
                self.write_ready(paths, node="compute007", gpu_index=2)
                value = json.loads(paths["ready"].read_text(encoding="utf-8"))
                value.update(replacement)
                paths["ready"].write_text(json.dumps(value) + "\n", encoding="utf-8")
                os.chmod(paths["ready"], 0o600)
                metadata = self.active_metadata(paths["workspaces"] / "course-aaaaaaaaaaaa")
                job = {
                    "job_id": "314",
                    "owner": "edu001",
                    "state": "RUNNING",
                    "node": "compute007",
                    "name": "ksc26-jlab-edu001",
                }
                with mock.patch.object(MODULE, "query_job", return_value=job), mock.patch.object(
                    MODULE, "authenticated_http_ready", return_value=True
                ) as http_ready:
                    state, _ = MODULE.session_status(metadata, "edu001", paths)
                self.assertEqual(state, "STARTING")
                http_ready.assert_not_called()

    def test_job_payload_guards_process_group_cleanup(self) -> None:
        script = (ROOT / "jupyter-job.sh").read_text(encoding="utf-8")
        for marker in (
            "wait_for_own_process_group()",
            'setsid "$KSC_APPTAINER"',
            'if [[ "$child_group_verified" == 1 ]] && is_own_process_group "$child_pid"',
            'kill -TERM -- "-$child_pid"',
        ):
            self.assertIn(marker, script)

    def test_job_payload_fails_closed_on_log_and_port_collisions(self) -> None:
        script = (ROOT / "jupyter-job.sh").read_text(encoding="utf-8")
        for marker in (
            '[[ ! -e "$log_file" && ! -L "$log_file" ]]',
            "set -o noclobber",
            'stat -c \'%u:%a:%h\' -- "$log_file"',
            's.bind(("0.0.0.0", int(sys.argv[1])))',
            "c.ServerApp.port_retries = 0",
        ):
            self.assertIn(marker, script)


if __name__ == "__main__":
    unittest.main()
