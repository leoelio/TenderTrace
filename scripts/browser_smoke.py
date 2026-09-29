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
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(url, wait_until="networkidle", timeout=30000)

        primary_labels = page.locator("#topNavigation > .nav-tab").all_inner_texts()
        if primary_labels != ["首页", "查招标", "投标项目", "团队协作"]:
            print(f"FAIL: primary navigation is not the simplified workflow: {primary_labels!r}")
            return 1
        print("OK  primary navigation follows the core tender workflow")

        page.locator('#topNavigation > [data-view="workbenchView"]').click()

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

        edit_button = page.locator("[data-edit-intent]")
        if edit_button.count() != 1:
            print("FAIL: inline clarification edit action not shown")
            return 1
        edit_button.click()
        if page.evaluate("document.activeElement?.id") != "queryInput":
            print("FAIL: clarification edit action did not return focus to query input")
            return 1
        print("OK  inline clarification actions are available and editable")

        page.evaluate(
            "document.querySelector('#runForm').addEventListener('submit', event => event.preventDefault(), {capture: true, once: true})"
        )
        page.locator("[data-confirm-intent]").click()
        page.locator(".clarify-chip.is-confirmed").wait_for(timeout=5000)
        print("OK  inline clarification confirmation is recorded before submission")

        page.locator("#topNavigation .nav-more > summary").click()
        page.locator('#topNavigation [data-view="evaluationView"]').click()
        page.locator("#evaluationCases [data-annotate-gold-case]").first.wait_for(timeout=8000)
        page.locator("#evaluationCases [data-annotate-gold-case]").first.click()
        annotation_dialog = page.locator("#goldAnnotationDialog")
        if not annotation_dialog.evaluate("element => element.open"):
            print("FAIL: gold annotation dialog did not open")
            return 1
        if not page.locator("#goldAnnotationSourceUrl").evaluate("element => element.required"):
            print("FAIL: gold annotation source URL is not required")
            return 1
        page.locator("#cancelGoldAnnotationButton").click()
        print("OK  human gold annotation requires an explicit verified source URL")

        page.locator("#topNavigation .nav-more > summary").click()
        page.locator("#presentationModeButton").click()
        exit_button = page.locator("#presentationExitButton")
        if not exit_button.is_visible():
            print("FAIL: presentation mode has no visible exit action")
            return 1
        exit_button.click()
        if page.locator("body.presentation-mode").count():
            print("FAIL: presentation exit action did not restore normal mode")
            return 1
        print("OK  presentation mode exposes and honors the fixed exit action")

        page.locator('#topNavigation > [data-view="opportunityView"]').click()
        refresh_button = page.locator("#refreshOpportunitiesButton")
        refresh_style = refresh_button.evaluate(
            "element => ({ color: getComputedStyle(element).color, background: getComputedStyle(element).backgroundColor })"
        )
        if refresh_button.inner_text().strip() != "刷新" or refresh_style["color"] == refresh_style["background"]:
            print(f"FAIL: project refresh action is unreadable: {refresh_style!r}")
            return 1
        if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
            print("FAIL: project view overflows horizontally")
            return 1
        print("OK  project actions are readable and the desktop layout has no horizontal overflow")

        page.locator('#topNavigation > [data-view="organizationView"]').click()
        create_group_button = page.locator("#createOrganizationWorkspaceButton")
        create_group_style = create_group_button.evaluate(
            "element => ({ color: getComputedStyle(element).color, background: getComputedStyle(element).backgroundColor })"
        )
        if create_group_button.inner_text().strip() != "创建项目群" or create_group_style["color"] == create_group_style["background"]:
            print(f"FAIL: create-group action is unreadable: {create_group_style!r}")
            return 1
        page.locator("#createOrganizationWorkspaceButton").click()
        group_dialog = page.locator("#organizationGroupDialog")
        group_dialog.wait_for(state="visible", timeout=8000)
        member_choices = page.locator("#organizationMemberPicker .organization-member-choice")
        if member_choices.count():
            member_choices.first.locator('input[type="checkbox"]').check()
            if "1" not in page.locator("#organizationMemberCount").inner_text():
                print("FAIL: custom member picker did not update the selected count")
                return 1
        page.locator("#cancelOrganizationGroupButton").click()
        workspace_id = page.locator("#organizationWorkspaceSelect").input_value()
        if workspace_id:
            page.locator("#inviteOrganizationMembersButton").click()
            group_dialog.wait_for(state="visible", timeout=8000)
            if "邀请协作成员" not in page.locator("#organizationGroupDialogTitle").inner_text():
                print("FAIL: invite mode did not render the expected dialog title")
                return 1
            if not page.locator("#organizationGroupNameField").is_hidden():
                print("FAIL: invite mode still exposes the create-group name field")
                return 1
            page.locator("#cancelOrganizationGroupButton").click()
        print("OK  organization member picker opens in create and invite modes")

        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.goto(url, wait_until="networkidle", timeout=30000)
        for view_id in ("finalsHomeView", "workbenchView", "opportunityView", "organizationView"):
            mobile.locator(f'[data-view="{view_id}"]').first.evaluate("element => element.click()")
            mobile.wait_for_timeout(250)
            if mobile.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                print(f"FAIL: {view_id} overflows on the 390px mobile viewport")
                return 1
        mobile.close()
        print("OK  all four primary views fit the mobile viewport")

        browser.close()
    print("PASS: browser smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/"))
