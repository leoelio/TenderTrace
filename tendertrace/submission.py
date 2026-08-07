from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import zipfile


ROOT_FILES = (
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "README.md",
    "pyproject.toml",
    "TenderTrace_implementation_plan.md",
    "TenderTrace_implementation_plan.docx",
)

SOURCE_DIRS = (
    ".github/workflows",
    "tendertrace",
    "tests",
    "docs",
    "web/dist",
)

RUNTIME_DOCX_DIRS = (
    "outputs",
    "outbox",
)

FORBIDDEN_NAMES = {
    ".env",
    ".env.local",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "data",
    "dist",
    "logs",
    "node_modules",
    "secrets",
    "snapshots",
    "tendertrace.egg-info",
    "traces",
    "venv",
}

FORBIDDEN_PREFIXES = (
    ".env.",
    "~$",
)

ALLOWED_SUFFIXES = {
    ".css",
    ".docx",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mp4",
    ".png",
    ".py",
    ".toml",
    ".txt",
    ".yml",
}

ALLOWED_FILENAMES = {
    ".env.example",
    ".gitattributes",
    ".gitignore",
}


@dataclass(frozen=True)
class SubmissionSecurityFinding:
    path: str
    kind: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SubmissionFile:
    path: str
    size: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SubmissionPackageResult:
    status: str
    package_path: str
    manifest_path: str
    file_count: int
    total_bytes: int
    forbidden_entry_count: int
    secret_hit_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def create_submission_package(root: Path, output_path: Path | None = None) -> SubmissionPackageResult:
    root = root.resolve()
    dist_dir = root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    package_path = output_path or dist_dir / f"TenderTrace_submission_{stamp}.zip"
    if not package_path.is_absolute():
        package_path = root / package_path
    package_path.parent.mkdir(parents=True, exist_ok=True)

    files = _collect_submission_files(root)
    manifest_files = [_file_record(root, path) for path in files]
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_path),
        "file_count": len(manifest_files),
        "total_bytes": sum(item.size for item in manifest_files),
        "forbidden_names": sorted(FORBIDDEN_NAMES),
        "files": [item.to_dict() for item in manifest_files],
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(root).as_posix())
        archive.writestr("SUBMISSION_MANIFEST.json", manifest_bytes)

    manifest_path = package_path.with_suffix(".manifest.json")
    manifest_path.write_bytes(manifest_bytes)
    forbidden = forbidden_package_entries(package_path)
    secret_findings = package_secret_findings(package_path)
    return SubmissionPackageResult(
        status="pass" if not forbidden and not secret_findings else "fail",
        package_path=str(package_path),
        manifest_path=str(manifest_path),
        file_count=len(manifest_files),
        total_bytes=sum(item.size for item in manifest_files),
        forbidden_entry_count=len(forbidden),
        secret_hit_count=len(secret_findings),
    )


def forbidden_package_entries(package_path: Path) -> list[str]:
    with zipfile.ZipFile(package_path) as archive:
        entries = archive.namelist()
    return [entry for entry in entries if _is_forbidden_relative(Path(entry))]


def package_secret_findings(package_path: Path) -> list[SubmissionSecurityFinding]:
    findings: list[SubmissionSecurityFinding] = []
    with zipfile.ZipFile(package_path) as archive:
        for entry in archive.infolist():
            if entry.is_dir() or not _is_scannable_entry(entry.filename, entry.file_size):
                continue
            text = archive.read(entry).decode("utf-8", errors="ignore")
            findings.extend(_scan_text(entry.filename, text))
    return findings


def _collect_submission_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for relative in ROOT_FILES:
        path = root / relative
        if path.is_file() and _is_allowed_file(path, root):
            files.append(path)
    for relative in SOURCE_DIRS:
        base = root / relative
        if base.exists():
            files.extend(path for path in base.rglob("*") if _is_allowed_file(path, root))
    for relative in RUNTIME_DOCX_DIRS:
        base = root / relative
        if base.exists():
            files.extend(path for path in base.glob("*.docx") if _is_allowed_file(path, root))
    return sorted(set(files), key=lambda path: path.relative_to(root).as_posix())


def _is_allowed_file(path: Path, root: Path) -> bool:
    if not path.is_file():
        return False
    relative = path.resolve().relative_to(root)
    if _is_forbidden_relative(relative):
        return False
    if path.name in ALLOWED_FILENAMES:
        return True
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        return False
    return True


def _is_forbidden_relative(relative: Path) -> bool:
    parts = relative.parts
    if relative.as_posix() == ".env.example":
        return False
    if parts and parts[0] == "dist":
        return True
    for index, part in enumerate(parts):
        if part == "dist" and index > 0 and parts[index - 1] == "web":
            continue
        if part in FORBIDDEN_NAMES:
            return True
        if any(part.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            return True
    return False


def _file_record(root: Path, path: Path) -> SubmissionFile:
    data = path.read_bytes()
    return SubmissionFile(
        path=path.relative_to(root).as_posix(),
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


SCANNABLE_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yml",
}

SECRET_VALUE_PATTERN = re.compile(
    r"""(?ix)
    (?P<key>
        api[_-]?key|app[_-]?secret|app[_-]?token|access[_-]?token|
        authorization|bearer|cookie|password|smtp[_-]?password|storage[_-]?state
    )
    [ \t"':=]+
    (?P<value>sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{16,}|[A-Za-z0-9._/\-+=]{20,})
    """
)

OPENAI_KEY_PATTERN = re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")


def _is_scannable_entry(filename: str, size: int) -> bool:
    return size <= 2_000_000 and Path(filename).suffix.lower() in SCANNABLE_SUFFIXES


def _scan_text(path: str, text: str) -> list[SubmissionSecurityFinding]:
    findings: list[SubmissionSecurityFinding] = []
    for match in OPENAI_KEY_PATTERN.finditer(text):
        value = match.group(0)
        if not _is_placeholder_value(value):
            findings.append(SubmissionSecurityFinding(path, "openai_key", "OpenAI key-like value"))
    if Path(path).suffix.lower() == ".py":
        return findings
    for match in SECRET_VALUE_PATTERN.finditer(text):
        key = match.group("key")
        value = match.group("value")
        if not _is_placeholder_value(value):
            findings.append(SubmissionSecurityFinding(path, key.lower(), f"{key} has a non-placeholder value"))
    return findings


def _is_placeholder_value(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in (
            "[redacted]",
            "example",
            "fake",
            "placeholder",
            "test",
            "secret",
            "xxxx",
            "...",
        )
    )
