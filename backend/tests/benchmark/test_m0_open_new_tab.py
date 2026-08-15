from benchmark.m0_executor import PlaywrightDriver


class _Response:
    status = 200


class _Page:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.goto_calls = []

    def goto(self, url, **kwargs):
        self.url = url
        self.goto_calls.append((url, kwargs))
        return _Response()


class _Context:
    def __init__(self) -> None:
        self.created = []

    def new_page(self):
        page = _Page()
        self.created.append(page)
        return page


def _driver() -> PlaywrightDriver:
    driver = object.__new__(PlaywrightDriver)
    driver._context = _Context()
    driver._page = _Page()
    driver._last_status = None
    return driver


def test_open_new_tab_uses_url_without_locator_resolution() -> None:
    driver = _driver()

    result = driver.execute_playwright({
        "action_type": "open_new_tab",
        "target_selector": "",
        "value": "https://example.test/source",
        "description": "Open grounded source",
    })

    assert result.success is True
    assert result.locator_attempts == 0
    assert driver._page.url == "https://example.test/source"
    assert len(driver._context.created) == 1


def test_open_new_tab_rejects_missing_url() -> None:
    result = _driver().execute_playwright({
        "action_type": "open_new_tab",
        "target_selector": "",
        "value": "",
        "description": "Open source",
    })

    assert result.success is False
    assert "valid http(s) url" in result.message
