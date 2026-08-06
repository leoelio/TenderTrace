import unittest

from selectolax.parser import HTMLParser

from tendertrace.parsing import select_main_content


class ParsingTests(unittest.TestCase):
    def test_select_main_content_falls_back_to_largest_text_block(self) -> None:
        parser = HTMLParser(
            """
            <html>
              <body>
                <nav>home search login</nav>
                <section class="unknown">
                  Project overview: this server procurement tender has a long factual body.
                  Budget and opening time are provided in the source detail page.
                </section>
                <div>short</div>
              </body>
            </html>
            """
        )

        selection = select_main_content(parser, ("#missing", ".also-missing"))

        self.assertTrue(selection.fallback_used)
        self.assertEqual(selection.selector, "fallback:section")
        self.assertIn("server procurement tender", selection.text)
        self.assertNotIn("home search login", selection.text)


if __name__ == "__main__":
    unittest.main()
