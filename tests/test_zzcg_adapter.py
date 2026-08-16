from __future__ import annotations

import unittest

from tendertrace.adapters.zzcg import ZzcgAdapter, parse_list_page


LIST_HTML = """
<html><body>
  <ul>
    <li>
      <span class="Gray Right">2026-08-14</span>
      <a href="http://www.zzcg.gov.cn:80/zbgg/17988.jhtml">
        北京电子科技学院服务器采购项目招标公告
      </a>
    </li>
    <li>
      <span class="Gray Right">2026-08-13</span>
      <a href="http://www.zzcg.gov.cn:80/zbgg/17987.jhtml">物业服务采购项目招标公告</a>
    </li>
  </ul>
</body></html>
"""


class ZzcgAdapterTests(unittest.TestCase):
    def test_parse_list_preserves_official_link_and_notice_metadata(self) -> None:
        notices = parse_list_page(LIST_HTML, "https://www.zzcg.gov.cn/zbgg/index.jhtml")

        self.assertEqual(len(notices), 2)
        notice = notices[0]
        self.assertEqual(notice.source_site, "zzcg")
        self.assertEqual(notice.publish_time, "2026-08-14")
        self.assertEqual(notice.region, "北京")
        self.assertEqual(notice.fields["notice_type"], "采购公告")
        self.assertEqual(notice.fields["authority"], "中共中央直属机关采购中心")
        self.assertEqual(notice.fields["content_format"], "official_image_notice")
        self.assertEqual(notice.source_url, "http://www.zzcg.gov.cn:80/zbgg/17988.jhtml")

    def test_page_routes_follow_the_site_static_pagination_contract(self) -> None:
        urls = ZzcgAdapter().list_urls(2)

        self.assertIn("https://www.zzcg.gov.cn/zbgg/index_2.jhtml", urls)
        self.assertIn("https://www.zzcg.gov.cn/jggg/index_2.jhtml", urls)

    def test_adapter_routes_only_domestic_scope(self) -> None:
        adapter = ZzcgAdapter()

        self.assertTrue(adapter.supports({"region": {"scope": "domestic"}}))
        self.assertFalse(adapter.supports({"region": {"scope": "eu"}}))


if __name__ == "__main__":
    unittest.main()
