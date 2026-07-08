from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from tendertrace.config import Settings
from tendertrace.demo_check import DemoEvidenceReport, run_demo_check, write_demo_evidence


@dataclass(frozen=True)
class DemoVideoResult:
    status: str
    output_path: str
    evidence_path: str
    frames: int
    warning_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


SLIDE_SIZE = (1280, 720)
FPS = 1
SECONDS_PER_SLIDE = 4


def generate_demo_video(
    settings: Settings,
    *,
    url: str,
    output_path: Path | None = None,
    evidence_path: Path | None = None,
) -> DemoVideoResult:
    output_path = output_path or _default_video_path(settings)
    evidence_path = evidence_path or settings.workspace_root / "docs" / "demo" / "demo_evidence_latest.json"
    frame_dir = settings.workspace_root / "docs" / "demo" / ".video_frames"
    screenshot_dir = frame_dir / "screenshots"
    _reset_dir(frame_dir)
    screenshot_paths = capture_web_screenshots(url, screenshot_dir)
    report = run_demo_check(settings)
    frames = render_demo_frames(report, screenshot_paths, frame_dir)
    _encode_video(frame_dir, output_path, len(frames))
    final_report = run_demo_check(settings)
    write_demo_evidence(final_report, evidence_path)
    _remove_dir(frame_dir)
    return DemoVideoResult(
        status=final_report.status,
        output_path=str(output_path),
        evidence_path=str(evidence_path),
        frames=len(frames),
        warning_count=sum(1 for check in final_report.checks if check.status == "warn"),
    )


def capture_web_screenshots(url: str, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for demo-video") from exc
    paths: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(url, wait_until="networkidle", timeout=30000)
        dashboard = output_dir / "dashboard.png"
        page.screenshot(path=str(dashboard), full_page=False)
        paths.append(dashboard)
        trace_buttons = page.locator("[data-run-id]")
        if trace_buttons.count():
            trace_buttons.first.click()
            page.wait_for_timeout(1200)
        trace = output_dir / "trace.png"
        page.screenshot(path=str(trace), full_page=False)
        paths.append(trace)
        browser.close()
    return paths


def render_demo_frames(
    report: DemoEvidenceReport,
    screenshot_paths: list[Path],
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence = report.evidence
    latest = evidence.get("latest_finished_run") or {}
    stats = latest.get("stats") or {}
    checks = {check.name: check for check in report.checks}
    slide_specs = [
        (
            "TenderTrace 招投标信息聚合工具",
            [
                "自然语言问题 -> 多源采集 -> 清洗去重 -> 证据校验 -> Word/outbox",
                f"Demo precheck: {report.status}, pass/warn/fail = {_counts_text(report)}",
            ],
            screenshot_paths[0] if screenshot_paths else None,
        ),
        (
            "输入与输出证据",
            [
                f"Finished runs: {evidence.get('finished_run_count', 0)}",
                f"Distinct queries: {evidence.get('distinct_finished_queries', 0)}",
                f"Latest query: {latest.get('original_query', '-')}",
                f"Word/outbox: {len(evidence.get('outputs_docx', []))} / {len(evidence.get('outbox_docx', []))}",
            ],
            screenshot_paths[0] if screenshot_paths else None,
        ),
        (
            "事件流与质量指标",
            [
                "Trace tools: " + ", ".join(evidence.get("latest_trace_tools", [])[:5]),
                f"Notices: {stats.get('notice_count', 0)}",
                f"Evidence passed: {stats.get('evidence_passed', 0)}",
                f"Attachments extracted: {stats.get('attachments_extracted', 0)}",
            ],
            screenshot_paths[1] if len(screenshot_paths) > 1 else None,
        ),
        (
            "订阅与增量不重复",
            [
                f"Active subscriptions: {evidence.get('active_subscription_count', 0)}",
                f"sent_history records: {evidence.get('sent_history_count', 0)}",
                _detail(checks, "subscription_incremental"),
            ],
            None,
        ),
        (
            "交付前透明剩余项",
            [
                _detail(checks, "sources"),
                _detail(checks, "demo_video_file"),
                "API key and account secrets are not shown in UI, docs, tests, or evidence package.",
            ],
            None,
        ),
    ]
    frame_paths: list[Path] = []
    for index, (title, lines, screenshot) in enumerate(slide_specs, start=1):
        slide = _render_slide(title, lines, screenshot)
        for repeat in range(SECONDS_PER_SLIDE * FPS):
            frame = output_dir / f"frame_{len(frame_paths):04d}.png"
            slide.save(frame)
            frame_paths.append(frame)
    return frame_paths


def _render_slide(title: str, lines: list[str], screenshot: Path | None) -> Image.Image:
    image = Image.new("RGB", SLIDE_SIZE, "#F6F8FB")
    draw = ImageDraw.Draw(image)
    title_font = _font(34, bold=True)
    body_font = _font(22)
    small_font = _font(16)
    draw.rectangle((0, 0, 1280, 86), fill="#FFFFFF")
    draw.text((48, 25), title, fill="#172033", font=title_font)
    y = 118
    for line in lines:
        draw.text((52, y), line, fill="#344054", font=body_font)
        y += 38
    if screenshot and screenshot.exists():
        with Image.open(screenshot) as shot:
            shot = shot.convert("RGB")
            shot.thumbnail((1160, 360))
            x = (1280 - shot.width) // 2
            image.paste(shot, (x, 320))
            draw.rectangle((x, 320, x + shot.width, 320 + shot.height), outline="#D9E0EA", width=2)
    draw.text((52, 680), "TenderTrace demo evidence video", fill="#667085", font=small_font)
    return image


def _encode_video(frame_dir: Path, output_path: Path, frame_count: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for demo-video")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-framerate",
        str(FPS),
        "-i",
        str(frame_dir / "frame_%04d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {completed.stderr[-800:]}")


def _default_video_path(settings: Settings) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    return settings.workspace_root / "docs" / "demo" / f"TenderTrace_Demo_{stamp}.mp4"


def _reset_dir(path: Path) -> None:
    _remove_dir(path)
    path.mkdir(parents=True, exist_ok=True)


def _remove_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _counts_text(report: DemoEvidenceReport) -> str:
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for check in report.checks:
        counts[check.status] += 1
    return f"{counts['pass']}/{counts['warn']}/{counts['fail']}"


def _detail(checks: dict[str, Any], name: str) -> str:
    check = checks.get(name)
    return check.detail if check else f"{name}: missing"
