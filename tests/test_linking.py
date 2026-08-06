import unittest

from tendertrace.linking import LinkExtractor


class LinkExtractorTests(unittest.TestCase):
    def test_extracts_allowed_same_domain_detail_and_attachment_links(self) -> None:
        html = """
        <html><body>
          <a href="/information/deal/html/a/1.html">detail</a>
          <a href="/information/deal/html/a/1.html?utm_source=x">duplicate</a>
          <a href="/files/spec.pdf">attachment</a>
          <a href="/login">login</a>
          <a href="https://other.example.com/page.html">other</a>
        </body></html>
        """
        extractor = LinkExtractor(
            allow=(r"/information/deal/html/.+\.html$", r"\.pdf$"),
            deny=(r"/login",),
        )

        links = extractor.extract(html, "https://www.ggzy.gov.cn/deal/dealList.html")

        self.assertEqual([link.kind for link in links], ["detail", "attachment"])
        self.assertEqual(
            links[0].url,
            "https://www.ggzy.gov.cn/information/deal/html/a/1.html",
        )
        self.assertEqual(links[1].url, "https://www.ggzy.gov.cn/files/spec.pdf")


if __name__ == "__main__":
    unittest.main()
