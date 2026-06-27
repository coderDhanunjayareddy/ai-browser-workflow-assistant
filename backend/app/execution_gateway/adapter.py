"""
Phase B — Execution Gateway V1 — Adapter Interface.

The PERMANENT adapter API. Every future browser adapter (Playwright, Chrome CDP,
native extension, vision) implements exactly this interface. The gateway dispatches
abstract ExecutionCommands; the adapter turns them into (eventually) real actions.

V1 ships ONLY this interface plus a deterministic MockBrowserAdapter (mock_adapter.py).
There is NO browser code here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.execution_gateway.models import AdapterResult, CommandType, ExecutionCommand


class ExecutionAdapter(ABC):
    """
    Abstract execution adapter — the single contract all adapters honor.

    Each method takes an ExecutionCommand and returns an AdapterResult.
    Implementations MUST be side-effect-free with respect to this codebase
    (they talk to a browser, not to our registries).
    """

    #: Human-readable adapter name (e.g. "mock", "playwright").
    name: str = "abstract"

    # ── the 9 permanent adapter operations ────────────────────────────────────

    @abstractmethod
    def navigate(self, command: ExecutionCommand) -> AdapterResult: ...

    @abstractmethod
    def click(self, command: ExecutionCommand) -> AdapterResult: ...

    @abstractmethod
    def type(self, command: ExecutionCommand) -> AdapterResult: ...

    @abstractmethod
    def wait(self, command: ExecutionCommand) -> AdapterResult: ...

    @abstractmethod
    def extract(self, command: ExecutionCommand) -> AdapterResult: ...

    @abstractmethod
    def validate(self, command: ExecutionCommand) -> AdapterResult: ...

    @abstractmethod
    def upload(self, command: ExecutionCommand) -> AdapterResult: ...

    @abstractmethod
    def download(self, command: ExecutionCommand) -> AdapterResult: ...

    @abstractmethod
    def execute_custom(self, command: ExecutionCommand) -> AdapterResult: ...

    # ── routing ───────────────────────────────────────────────────────────────

    #: command_type → adapter method name. Permanent routing table.
    COMMAND_ROUTING: dict[CommandType, str] = {
        CommandType.navigate: "navigate",
        CommandType.click:    "click",
        CommandType.type:     "type",
        CommandType.wait:     "wait",
        CommandType.extract:  "extract",
        CommandType.validate: "validate",
        CommandType.upload:   "upload",
        CommandType.download: "download",
        CommandType.custom:   "execute_custom",
    }

    def dispatch(self, command: ExecutionCommand) -> AdapterResult:
        """Route a command to the matching adapter method. No browser code here."""
        method_name = self.COMMAND_ROUTING.get(command.command_type, "execute_custom")
        method = getattr(self, method_name)
        return method(command)
