from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from app.certification.fixtures import FixtureServer


FIXTURE = Path(__file__).resolve().parents[3] / "docs" / "production_validation" / "day4" / "fixtures" / "synthetic-day4.txt"


@pytest.fixture(scope="module")
def server():
    instance = FixtureServer().start()
    try:
        yield instance
    finally:
        instance.stop()


def test_effect_classes_are_declared_and_preview_does_not_send(server) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(server.base_url + "/content-insertion")

        page.locator("#content-file").set_input_files(str(FIXTURE))
        preview = page.locator("#content-preview").inner_text()
        assert FIXTURE.name in preview
        assert "text/plain" in preview
        assert str(FIXTURE.stat().st_size) in preview
        assert page.locator("#send-count").inner_text() == "0"

        assert page.locator("#gif-immediate").get_attribute("data-insertion-effect") == "selection_sends_immediately"
        assert page.locator("#emoji-insert").get_attribute("data-insertion-effect") == "inserts_into_composer"
        assert page.locator("#poll-draft").get_attribute("data-insertion-effect") == "structured_draft"
        assert page.locator("#camera-capture").get_attribute("data-insertion-effect") == "device_capture"
        assert page.locator("#immediate-count").inner_text() == "0"

        page.locator("#emoji-insert").click()
        assert page.locator("#composer").input_value() == "🙂"
        assert page.locator("#immediate-count").inner_text() == "0"

        page.locator("#poll-draft").click()
        assert page.locator("#draft-state").inner_text() == "Poll draft opened"
        assert page.locator("#send-count").inner_text() == "0"
        browser.close()
