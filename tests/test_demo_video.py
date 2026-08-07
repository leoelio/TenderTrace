from pathlib import Path
import tempfile
import unittest

from PIL import Image

from tendertrace.demo_check import DemoCheck, DemoEvidenceReport
from tendertrace.demo_video import DemoVideoResult, render_demo_frames


class DemoVideoTests(unittest.TestCase):
    def test_render_demo_frames_uses_report_evidence_and_screenshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screenshot = root / "dashboard.png"
            Image.new("RGB", (800, 500), "#ffffff").save(screenshot)
            report = DemoEvidenceReport(
                status="pass",
                generated_at="2026-07-06T21:00:00",
                checks=[
                    DemoCheck("subscription_incremental", "pass", "1 active subscription"),
                    DemoCheck("sources", "warn", "qianlima login_required"),
                    DemoCheck("demo_video_file", "warn", "no demo video file found"),
                ],
                evidence={
                    "finished_run_count": 2,
                    "distinct_finished_queries": 2,
                    "outputs_docx": ["a.docx"],
                    "outbox_docx": ["a.docx"],
                    "latest_finished_run": {
                        "original_query": "最近7天全国服务器招标信息都有哪些",
                        "stats": {
                            "notice_count": 2,
                            "evidence_passed": 2,
                            "attachments_extracted": 0,
                        },
                    },
                    "latest_trace_tools": [
                        "intent.rule_parser",
                        "adapter.multi.collect",
                        "pipeline.clean_dedup",
                    ],
                    "active_subscription_count": 1,
                    "sent_history_count": 1,
                },
            )

            frames = render_demo_frames(report, [screenshot], root / "frames")

        self.assertEqual(len(frames), 20)
        self.assertTrue(all(frame.name.startswith("frame_") for frame in frames))
        self.assertTrue(all(frame.suffix == ".png" for frame in frames))

    def test_demo_video_result_is_json_safe(self) -> None:
        result = DemoVideoResult(
            status="pass",
            output_path="docs/demo/demo演示视频.mp4",
            evidence_path="docs/demo/demo_evidence_latest.json",
            frames=20,
            warning_count=1,
        )

        self.assertEqual(result.to_dict()["output_path"], "docs/demo/demo演示视频.mp4")
        self.assertEqual(result.to_dict()["warning_count"], 1)


if __name__ == "__main__":
    unittest.main()
