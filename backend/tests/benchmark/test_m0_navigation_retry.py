from benchmark.m0_executor import PlaywrightDriver
from benchmark.recovery_engine import RecoveryHistory


class _Response:
    status = 200


class _Page:
    def __init__(self) -> None:
        self.calls = 0
        self.waits: list[int] = []

    def goto(self, url: str, *, wait_until: str, timeout: int):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR")
        return _Response()

    def wait_for_timeout(self, value: int) -> None:
        self.waits.append(value)


def test_navigation_retries_one_transient_protocol_failure() -> None:
    driver = object.__new__(PlaywrightDriver)
    driver._page = _Page()
    driver._last_status = None
    driver._recovery_history = RecoveryHistory()

    driver.navigate("https://example.test")

    assert driver._page.calls == 2
    assert driver._page.waits == [500]
    assert driver.last_navigation_status() == 200
