from __future__ import annotations

from dataclasses import asdict, dataclass

from tendertrace.config import ModelMode, Settings
from tendertrace.llm.gateway import ModelGateway, model_status


@dataclass(frozen=True)
class ModelDoctorCheck:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ModelDoctorReport:
    status: str
    live: bool
    checks: list[ModelDoctorCheck]

    def to_dict(self) -> dict[str, object]:
        counts = {"pass": 0, "warn": 0, "fail": 0}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        return {
            "status": self.status,
            "live": self.live,
            "counts": counts,
            "checks": [check.to_dict() for check in self.checks],
        }


def model_doctor(
    settings: Settings,
    *,
    live: bool = False,
    gateway: ModelGateway | None = None,
) -> ModelDoctorReport:
    checks: list[ModelDoctorCheck] = []
    status = model_status(settings)
    checks.append(
        ModelDoctorCheck(
            "provider",
            "pass" if status.configured else "fail",
            f"{status.mode}/{status.provider}/{status.model or 'none'}",
        )
    )
    checks.append(_mode_dependency_check(settings))
    checks.append(_enhancement_check(settings))
    if live:
        checks.append(_live_probe(gateway or ModelGateway(settings)))
    report_status = "fail" if any(check.status == "fail" for check in checks) else "pass"
    return ModelDoctorReport(status=report_status, live=live, checks=checks)


def _mode_dependency_check(settings: Settings) -> ModelDoctorCheck:
    if settings.model_mode == ModelMode.CLOUD:
        return ModelDoctorCheck(
            "local_dependency",
            "pass",
            "Ollama is not required while TENDERTRACE_MODEL_MODE=cloud",
        )
    if settings.model_mode == ModelMode.DISABLED:
        return ModelDoctorCheck(
            "local_dependency",
            "pass",
            "no model provider is required while TENDERTRACE_MODEL_MODE=disabled",
        )
    return ModelDoctorCheck(
        "local_dependency",
        "pass",
        "Ollama is required only when local enhancement is enabled and invoked",
    )


def _enhancement_check(settings: Settings) -> ModelDoctorCheck:
    if settings.model_enhancement_enabled:
        return ModelDoctorCheck("enhancement", "pass", "model enhancement is enabled")
    return ModelDoctorCheck(
        "enhancement",
        "warn",
        "model enhancement is disabled; runs will use deterministic rule parsing",
    )


def _live_probe(gateway: ModelGateway) -> ModelDoctorCheck:
    result = gateway.generate_json(
        system="Return only a compact JSON object. Do not include markdown.",
        user='Return exactly this JSON shape with any true boolean: {"ok": true}.',
    )
    if result.status == "ok":
        return ModelDoctorCheck(
            "live_probe",
            "pass",
            f"{result.provider}/{result.model} returned JSON in {result.latency_ms} ms",
        )
    if result.status == "skipped":
        return ModelDoctorCheck("live_probe", "warn", result.error)
    return ModelDoctorCheck("live_probe", "fail", result.error or "model probe failed")
