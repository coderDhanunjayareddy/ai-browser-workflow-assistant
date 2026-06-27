"""
Phase B — Execution Gateway V1 — Adapter Contract & Future Adapters.

Defines the PERMANENT adapter API surface and declares the future adapter classes
as interface-only stubs. These exist so callers can reference the eventual adapter
types today; every method raises NotImplementedError until its milestone lands.

CONSTRAINT: V1 ships NO browser code. Playwright / Chrome DevTools / Selenium /
Puppeteer / DOM / vision / OCR are explicitly out of scope. These stubs MUST stay
unimplemented in Phase B.
"""
from __future__ import annotations

from app.execution_gateway.adapter import ExecutionAdapter
from app.execution_gateway.models import AdapterResult, ExecutionCommand

# The permanent adapter operation set (documented for future implementers).
ADAPTER_OPERATIONS: tuple[str, ...] = (
    "navigate", "click", "type", "wait", "extract",
    "validate", "upload", "download", "execute_custom",
)


class _UnimplementedAdapter(ExecutionAdapter):
    """
    Base for not-yet-built adapters. Concrete in the abstract-method sense (so it can
    be instantiated for capability checks) but every operation refuses to run.
    """
    name = "unimplemented"

    def _refuse(self, command: ExecutionCommand) -> AdapterResult:
        raise NotImplementedError(
            f"{self.name} adapter is not implemented in Phase B (mock-only)."
        )

    def navigate(self, command: ExecutionCommand) -> AdapterResult:       return self._refuse(command)
    def click(self, command: ExecutionCommand) -> AdapterResult:          return self._refuse(command)
    def type(self, command: ExecutionCommand) -> AdapterResult:           return self._refuse(command)
    def wait(self, command: ExecutionCommand) -> AdapterResult:           return self._refuse(command)
    def extract(self, command: ExecutionCommand) -> AdapterResult:        return self._refuse(command)
    def validate(self, command: ExecutionCommand) -> AdapterResult:       return self._refuse(command)
    def upload(self, command: ExecutionCommand) -> AdapterResult:         return self._refuse(command)
    def download(self, command: ExecutionCommand) -> AdapterResult:       return self._refuse(command)
    def execute_custom(self, command: ExecutionCommand) -> AdapterResult: return self._refuse(command)


class PlaywrightAdapter(_UnimplementedAdapter):
    """FUTURE: drives a real browser via Playwright. Not implemented in Phase B."""
    name = "playwright"


class ChromeCDPAdapter(_UnimplementedAdapter):
    """FUTURE: drives Chrome via the DevTools Protocol. Not implemented in Phase B."""
    name = "chrome_cdp"


class NativeChromeExtensionAdapter(_UnimplementedAdapter):
    """FUTURE: dispatches through the native Chrome extension. Not implemented in Phase B."""
    name = "native_chrome_extension"


class VisionAdapter(_UnimplementedAdapter):
    """FUTURE: pixel/vision-based action adapter. Not implemented in Phase B."""
    name = "vision"


# Registry of known future adapters (names only — none are runnable yet).
FUTURE_ADAPTERS: dict[str, type] = {
    "playwright":              PlaywrightAdapter,
    "chrome_cdp":              ChromeCDPAdapter,
    "native_chrome_extension": NativeChromeExtensionAdapter,
    "vision":                  VisionAdapter,
}
