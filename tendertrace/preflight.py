from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable

from tendertrace.config import Settings


CommandRunner = Callable[[list[str], Path, int], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class PreflightStep:
    name: str
    status: str
    command: list[str]
    returncode: int | None
    detail: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PreflightReport:
    status: str
    steps: list[PreflightStep]

    def to_dict(self) -> dict[str, object]:
        counts = {"pass": 0, "skipped": 0, "fail": 0}
        for step in self.steps:
            counts[step.status] = counts.get(step.status, 0) + 1
        return {
            "status": self.status,
            "counts": counts,
            "steps": [step.to_dict() for step in self.steps],
        }


def run_preflight(
    settings: Settings,
    *,
    package: bool = True,
    live: bool = False,
    command_runner: CommandRunner | None = None,
) -> PreflightReport:
    runner = command_runner or _run_command
    python = sys.executable
    commands = [
        ("ruff", [python, "-m", "ruff", "check", "."], 120),
        ("pytest", [python, "-m", "pytest"], 240),
        ("acceptance", [python, "-m", "tendertrace", "acceptance-check"], 120),
        (
            "demo_check",
            [
                python,
                "-m",
                "tendertrace",
                "demo-check",
                "--out",
                "docs/demo/demo_evidence_latest.json",
            ],
            120,
        ),
    ]
    if live:
        commands.extend(
            [
                ("model_live", [python, "-m", "tendertrace", "model-doctor", "--live"], 120),
                (
                    "qianlima_live",
                    [python, "-m", "tendertrace", "verify-qianlima", "--live"],
                    180,
                ),
                (
                    "feishu_live",
                    [python, "-m", "tendertrace", "feishu-bitable-check"],
                    120,
                ),
            ]
        )
    steps = [_execute(name, command, settings.workspace_root, timeout, runner) for name, command, timeout in commands]
    node = _find_node()
    if node:
        steps.append(
            _execute(
                "frontend_syntax",
                [node, "--check", "web/dist/app.js"],
                settings.workspace_root,
                60,
                runner,
            )
        )
    else:
        steps.append(
            PreflightStep(
                name="frontend_syntax",
                status="skipped",
                command=["node", "--check", "web/dist/app.js"],
                returncode=None,
                detail="node executable not found on PATH",
            )
        )
    if package:
        steps.append(
            _execute(
                "package_submission",
                [python, "-m", "tendertrace", "package-submission"],
                settings.workspace_root,
                120,
                runner,
            )
        )
    status = "fail" if any(step.status == "fail" for step in steps) else "pass"
    return PreflightReport(status=status, steps=steps)


def _find_node() -> str | None:
    node = shutil.which("node")
    if node:
        return node
    bundled_dir = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
    )
    for name in ("node.exe", "node"):
        candidate = bundled_dir / name
        if candidate.exists():
            return str(candidate)
    return None


def _execute(
    name: str,
    command: list[str],
    cwd: Path,
    timeout: int,
    runner: CommandRunner,
) -> PreflightStep:
    try:
        completed = runner(command, cwd, timeout)
    except subprocess.TimeoutExpired:
        return PreflightStep(name, "fail", command, None, f"timed out after {timeout}s")
    detail = _command_detail(completed)
    return PreflightStep(
        name=name,
        status="pass" if completed.returncode == 0 else "fail",
        command=command,
        returncode=completed.returncode,
        detail=detail,
    )


def _run_command(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def _command_detail(completed: subprocess.CompletedProcess[str]) -> str:
    text = (completed.stdout or "").strip()
    if not text:
        return "ok" if completed.returncode == 0 else "no output"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[-1][:300] if lines else text[:300]
    if isinstance(payload, dict):
        if payload.get("status"):
            return f"status={payload['status']}"
        if payload.get("package_path"):
            return f"package={Path(str(payload['package_path'])).name}"
    return text[:300]
