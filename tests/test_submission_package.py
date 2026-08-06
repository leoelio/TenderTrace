from pathlib import Path
import tempfile
import unittest
import zipfile

from tendertrace.submission import create_submission_package, forbidden_package_entries


class SubmissionPackageTests(unittest.TestCase):
    def test_submission_package_includes_deliverables_and_excludes_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "README.md", "# TenderTrace\n")
            _write(root / "pyproject.toml", "[project]\nname='tendertrace'\n")
            _write(root / ".env.example", "OPENAI_API_KEY=\n")
            _write(root / ".env.local", "OPENAI_API_KEY=sk-proj-secret\n")
            _write(root / "secrets" / "qianlima_storage_state.json", '{"cookies":[{"value":"secret"}]}')
            _write(root / "data" / "tendertrace.sqlite3", "runtime")
            _write(root / "tendertrace" / "__init__.py", '"""package"""')
            _write(root / "tests" / "test_smoke.py", "def test_smoke(): pass\n")
            _write(root / "web" / "dist" / "app.js", "console.log('ok')\n")
            _write(root / "outputs" / "report.docx", "docx")
            _write(root / "outbox" / "report.docx", "docx")
            _write(root / "docs" / "demo" / "TenderTrace_Demo.mp4", "video")

            result = create_submission_package(root)
            forbidden = forbidden_package_entries(Path(result.package_path))
            with zipfile.ZipFile(result.package_path) as archive:
                entries = set(archive.namelist())

        self.assertEqual(result.status, "pass")
        self.assertEqual(forbidden, [])
        self.assertIn("web/dist/app.js", entries)
        self.assertIn(".env.example", entries)
        self.assertIn("outputs/report.docx", entries)
        self.assertIn("outbox/report.docx", entries)
        self.assertIn("docs/demo/TenderTrace_Demo.mp4", entries)
        self.assertIn("SUBMISSION_MANIFEST.json", entries)
        self.assertNotIn(".env.local", entries)
        self.assertFalse(any(entry.startswith("secrets/") for entry in entries))
        self.assertFalse(any(entry.startswith("data/") for entry in entries))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
