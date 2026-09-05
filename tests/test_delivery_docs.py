from pathlib import Path
import re
import unittest


class DeliveryDocsTests(unittest.TestCase):
    def test_required_delivery_documents_exist(self) -> None:
        required = [
            Path("docs/design/详设文档.md"),
            Path("docs/operation/操作文档.md"),
            Path("docs/demo/Demo演示脚本.md"),
            Path("docs/operation/P11_交付文档与验收包.md"),
            Path("docs/teaching/11_交付文档与验收包.md"),
            Path("docs/teaching/11_交付文档与验收包.docx"),
            Path("docs/operation/P12_验收Harness与交付审计.md"),
            Path("docs/teaching/12_验收Harness与交付审计.md"),
            Path("docs/teaching/12_验收Harness与交付审计.docx"),
            Path("docs/operation/P13_交付收口与完成度审计.md"),
            Path("docs/teaching/13_交付收口与完成度审计.md"),
            Path("docs/teaching/13_交付收口与完成度审计.docx"),
            Path("docs/operation/P14_本地模型自检与云端隔离.md"),
            Path("docs/teaching/14_本地模型自检与云端隔离.md"),
            Path("docs/teaching/14_本地模型自检与云端隔离.docx"),
            Path("docs/operation/P15_Demo预检与录屏证据包.md"),
            Path("docs/teaching/15_Demo预检与录屏证据包.md"),
            Path("docs/teaching/15_Demo预检与录屏证据包.docx"),
            Path("docs/operation/P16_Demo视频生成与交付闭环.md"),
            Path("docs/teaching/16_Demo视频生成与交付闭环.md"),
            Path("docs/teaching/16_Demo视频生成与交付闭环.docx"),
            Path("docs/operation/P17_登录源状态校验与千里马验收.md"),
            Path("docs/teaching/17_登录源状态校验与千里马验收.md"),
            Path("docs/teaching/17_登录源状态校验与千里马验收.docx"),
            Path("docs/operation/P18_安全提交包与最终打包.md"),
            Path("docs/teaching/18_安全提交包与最终打包.md"),
            Path("docs/teaching/18_安全提交包与最终打包.docx"),
            Path("docs/operation/P19_UI体验与检索召回优化.md"),
            Path("docs/teaching/19_UI体验与检索召回优化.md"),
            Path("docs/teaching/19_UI体验与检索召回优化.docx"),
            Path("docs/operation/P20_真实进度与地域降级说明.md"),
            Path("docs/teaching/20_真实进度与地域降级说明.md"),
            Path("docs/teaching/20_真实进度与地域降级说明.docx"),
            Path("docs/operation/P21_导航工作台删除与Agent评测.md"),
            Path("docs/teaching/21_导航工作台删除与Agent评测.md"),
            Path("docs/teaching/21_导航工作台删除与Agent评测.docx"),
            Path("docs/operation/P22_本地库检索与意图解析增强.md"),
            Path("docs/teaching/22_本地库检索与意图解析增强.md"),
            Path("docs/teaching/22_本地库检索与意图解析增强.docx"),
            Path("docs/operation/P23_金标召回评测与向量增强.md"),
            Path("docs/teaching/23_金标召回评测与向量增强.md"),
            Path("docs/teaching/23_金标召回评测与向量增强.docx"),
            Path("docs/delivery/交付清单.md"),
            Path("docs/delivery/完成度审计.md"),
            Path("docs/demo/demo_evidence_latest.json"),
        ]
        for path in required:
            with self.subTest(path=str(path)):
                self.assertTrue(path.exists(), f"missing delivery document: {path}")
                self.assertGreater(path.stat().st_size, 500)
        demo_videos = [
            path
            for path in Path("docs/demo").glob("*")
            if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm"}
        ]
        self.assertTrue(demo_videos, "missing demo video")
        self.assertGreater(max(path.stat().st_size for path in demo_videos), 10_000)

    def test_readme_matches_current_stage(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("Current stage: P52", readme)
        self.assertIn("407 automated tests pass", readme)
        self.assertIn("16 sources", readme)
        self.assertIn("acceptance-check", readme)

    def test_delivery_docs_do_not_regress_to_stale_evidence(self) -> None:
        banned = [
            "TenderTrace_Demo.mp4",
            "89 个单元测试",
            "95 个单元测试",
            "103 项单元测试",
            "pass=31",
            "pass: 31",
        ]
        paths = [Path("README.md"), Path("标迹TenderTrace报名补充材料.md")]
        paths.extend(Path("docs").rglob("*.md"))
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for marker in banned:
                with self.subTest(path=str(path), marker=marker):
                    self.assertNotIn(marker, text)

    def test_delivery_documents_do_not_contain_plaintext_openai_keys(self) -> None:
        secret_pattern = re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")
        paths = [
            Path("README.md"),
            Path(".env.example"),
            Path("docs/design/详设文档.md"),
            Path("docs/operation/操作文档.md"),
            Path("docs/demo/Demo演示脚本.md"),
            Path("docs/operation/P11_交付文档与验收包.md"),
            Path("docs/teaching/11_交付文档与验收包.md"),
            Path("docs/operation/P12_验收Harness与交付审计.md"),
            Path("docs/teaching/12_验收Harness与交付审计.md"),
            Path("docs/operation/P13_交付收口与完成度审计.md"),
            Path("docs/teaching/13_交付收口与完成度审计.md"),
            Path("docs/operation/P14_本地模型自检与云端隔离.md"),
            Path("docs/teaching/14_本地模型自检与云端隔离.md"),
            Path("docs/operation/P15_Demo预检与录屏证据包.md"),
            Path("docs/teaching/15_Demo预检与录屏证据包.md"),
            Path("docs/operation/P16_Demo视频生成与交付闭环.md"),
            Path("docs/teaching/16_Demo视频生成与交付闭环.md"),
            Path("docs/operation/P17_登录源状态校验与千里马验收.md"),
            Path("docs/teaching/17_登录源状态校验与千里马验收.md"),
            Path("docs/operation/P18_安全提交包与最终打包.md"),
            Path("docs/teaching/18_安全提交包与最终打包.md"),
            Path("docs/operation/P19_UI体验与检索召回优化.md"),
            Path("docs/teaching/19_UI体验与检索召回优化.md"),
            Path("docs/operation/P20_真实进度与地域降级说明.md"),
            Path("docs/teaching/20_真实进度与地域降级说明.md"),
            Path("docs/operation/P21_导航工作台删除与Agent评测.md"),
            Path("docs/teaching/21_导航工作台删除与Agent评测.md"),
            Path("docs/operation/P22_本地库检索与意图解析增强.md"),
            Path("docs/teaching/22_本地库检索与意图解析增强.md"),
            Path("docs/operation/P23_金标召回评测与向量增强.md"),
            Path("docs/teaching/23_金标召回评测与向量增强.md"),
            Path("docs/demo/demo_evidence_latest.json"),
            Path("docs/delivery/交付清单.md"),
            Path("docs/delivery/完成度审计.md"),
        ]
        for path in paths:
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(secret_pattern.search(text))

    def test_env_example_keeps_openai_key_blank(self) -> None:
        text = Path(".env.example").read_text(encoding="utf-8")
        self.assertIn("OPENAI_API_KEY=", text)
        self.assertNotRegex(text, r"OPENAI_API_KEY=\S+")


if __name__ == "__main__":
    unittest.main()
