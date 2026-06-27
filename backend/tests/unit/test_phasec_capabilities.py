"""Phase C — Unit tests: capabilities.py."""
import pytest
from app.execution_gateway.browser import capabilities as caps


class TestCapabilities:
    def test_supported_actions_count(self):
        assert len(caps.SUPPORTED_ACTIONS) == 11

    @pytest.mark.parametrize("action", [
        "NAVIGATE", "CLICK", "TYPE", "WAIT", "EXTRACT_TEXT", "EXTRACT_HTML",
        "UPLOAD", "DOWNLOAD", "VALIDATE_URL", "VALIDATE_TEXT", "VALIDATE_EXISTS",
    ])
    def test_action_supported(self, action):
        assert action in caps.SUPPORTED_ACTIONS

    def test_resolution_priority_order(self):
        assert caps.RESOLUTION_PRIORITY == (
            "selector", "testid", "aria_label", "role", "id", "name", "css", "xpath",
        )

    def test_context_supported(self):
        for k in ["multiple_tabs", "new_windows", "page_refresh", "popup_handling", "iframe_basic"]:
            assert caps.SUPPORTED_CONTEXT[k] is True

    def test_unsupported_yet(self):
        for k in ["cross_browser", "mobile", "persistent_profile", "drag_and_drop", "cloud_browser"]:
            assert caps.UNSUPPORTED_YET[k] is False

    def test_download_support(self):
        assert caps.DOWNLOAD_SUPPORT["download_detection"] is True
        assert caps.DOWNLOAD_SUPPORT["file_path_reporting"] is True
        assert caps.DOWNLOAD_SUPPORT["cloud_upload"] is False

    def test_upload_support(self):
        assert caps.UPLOAD_SUPPORT["input_file"] is True
        assert caps.UPLOAD_SUPPORT["multiple_files"] is True
        assert caps.UPLOAD_SUPPORT["drag_and_drop"] is False

    def test_get_capabilities(self):
        c = caps.get_capabilities()
        assert c["adapter"] == "playwright"
        assert c["browser"] == "chromium"
        assert c["ai_free"] is True
        for k in ["supported_actions", "resolution_priority", "context", "unsupported_yet",
                  "download", "upload"]:
            assert k in c

    def test_ai_free(self):
        assert caps.get_capabilities()["ai_free"] is True
