"""Headless browser smoke test for the TenderTrace Web workbench.

Usage (server must be running):

    python scripts/browser_smoke.py [http://127.0.0.1:8000/]

Verifies that the workbench loads, that a clear query renders an intent preview,
and that an ambiguous query surfaces the clarification chip.
"""

from __future__ import annotations

import sys


def main(url: str) -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)

        query_input = page.locator("#queryInput")
        if query_input.count() == 0:
            print("FAIL: #queryInput not found")
            return 1

        query_input.fill("最近一个月上海服务器招标信息")
        page.wait_for_timeout(1500)
        preview = page.locator("#intentPreview")
        preview_text = preview.inner_text() if preview.count() else ""
        if "上海" not in preview_text or "服务器" not in preview_text:
            print(f"FAIL: intent preview missing parsed region/topic: {preview_text!r}")
            return 1
        print(f"OK  clear-query intent preview: {preview_text!r}")

        query_input.fill("最近的信息")
        page.wait_for_timeout(1500)
        clarify = page.locator("#intentPreview.needs-clarification")
        if clarify.count() == 0:
            print(f"FAIL: clarification chip not shown for ambiguous query: {preview_text!r}")
            return 1
        print(f"OK  ambiguous-query clarification chip: {clarify.inner_text()!r}")

        browser.close()
    print("PASS: browser smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/"))
