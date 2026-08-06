import unittest

from tendertrace.adapters.ccgp import Attachment, Notice
from tendertrace.pipeline.dedup import (
    canonicalize_url,
    clean_and_cluster_notices,
    clean_text,
    extract_project_no,
    hamming_distance,
    simhash64,
)


class PipelineDedupTests(unittest.TestCase):
    def test_clean_text_removes_common_page_noise(self) -> None:
        text = clean_text("项目概况：采购服务器。 打印本页 关闭窗口 友情提示：请勿转载")

        self.assertEqual(text, "项目概况：采购服务器。")

    def test_canonicalize_url_removes_tracking_params_and_fragment(self) -> None:
        url = canonicalize_url("HTTPS://Example.COM/path?a=1&utm_source=x&b=2#top")

        self.assertEqual(url, "https://example.com/path?a=1&b=2")

    def test_simhash_is_stable_for_similar_text(self) -> None:
        left = simhash64("上海医院医疗设备采购项目公开招标公告")
        right = simhash64("上海医院医疗设备采购项目招标公告")

        self.assertLessEqual(hamming_distance(left, right), 12)

    def test_extract_project_no(self) -> None:
        self.assertEqual(
            extract_project_no("项目编号：SH-2026-001，预算金额：120万元"),
            "SH-2026-001",
        )

    def test_clean_and_cluster_merges_cross_source_duplicates(self) -> None:
        ccgp = Notice(
            id="ccgp-1",
            source_site="ccgp",
            title="上海某医院医疗设备采购项目公开招标公告",
            publish_time="2026-07-06 09:30",
            region="上海",
            purchaser="上海某医院",
            source_url="https://www.ccgp.gov.cn/detail.html?utm_source=x",
            content_text="项目编号：SH-2026-001。项目概况：医疗设备采购。打印本页",
            core_content="项目概况：医疗设备采购。",
            attachments=[Attachment(name="需求", url="https://example.com/spec.docx")],
        )
        ggzy = Notice(
            id="ggzy-1",
            source_site="ggzy",
            title="上海某医院医疗设备采购项目招标公告",
            publish_time="2026-07-06",
            region="上海市",
            purchaser="上海政府采购网",
            source_url="https://www.ggzy.gov.cn/detail.html",
            content_text="项目编号：SH-2026-001。项目概况：医疗设备采购。",
            core_content="项目概况：医疗设备采购。",
        )

        result = clean_and_cluster_notices([ccgp, ggzy])

        self.assertEqual(len(result.notices), 1)
        merged = result.notices[0]
        self.assertEqual(result.stats["duplicates_removed"], 1)
        self.assertEqual(merged.fields["cluster_key"], "project:sh-2026-001")
        self.assertEqual(merged.fields["duplicate_count"], 2)
        self.assertEqual(merged.fields["source_sites"], ["ccgp", "ggzy"])
        self.assertNotIn("打印本页", merged.content_text)
        self.assertEqual(len(merged.fields["related_sources"]), 2)


if __name__ == "__main__":
    unittest.main()
