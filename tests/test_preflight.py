from pathlib import Path
import subprocess
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.preflight import run_preflight


class PreflightTests(unittest.TestCase):
    def test_preflight_summarizes_command_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))

            report = run_preflight(settings, command_runner=_passing_runner, package=True)

        payload = report.to_dict()
        self.assertEqual(payload["status"], "pass")
        self.assertGreaterEqual(payload["counts"]["pass"], 4)
        self.assertIn("steps", payload)

    def test_preflight_fails_when_a_command_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))

            report = run_preflight(settings, command_runner=_failing_pytest_runner, package=False)

        self.assertEqual(report.status, "fail")
        failed = [step.name for step in report.steps if step.status == "fail"]
        self.assertEqual(failed, ["pytest"])

    def test_preflight_can_include_live_connectivity_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))

            report = run_preflight(
                settings,
                command_runner=_passing_runner,
                package=False,
                live=True,
            )

        names = [step.name for step in report.steps]
        self.assertIn("model_live", names)
        self.assertIn("qianlima_live", names)
        self.assertIn("feishu_live", names)


def _passing_runner(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 0, stdout='{"status":"pass"}\n')


def _failing_pytest_runner(
    command: list[str],
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    returncode = 1 if command[-1] == "pytest" else 0
    return subprocess.CompletedProcess(command, returncode, stdout="failed\n" if returncode else "ok\n")


if __name__ == "__main__":
    unittest.main()
