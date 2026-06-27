"""Phase B Execution Gateway — Unit tests: adapter.py, mock_adapter.py, contracts.py."""
import pytest
from app.execution_gateway.adapter import ExecutionAdapter
from app.execution_gateway.mock_adapter import MockBrowserAdapter, SIMULATED_DURATION_MS
from app.execution_gateway.models import CommandType, make_command
from app.execution_gateway.contracts import (
    PlaywrightAdapter, ChromeCDPAdapter, NativeChromeExtensionAdapter, VisionAdapter,
    FUTURE_ADAPTERS, ADAPTER_OPERATIONS,
)


def _cmd(ctype=CommandType.navigate, step_id="step-1"):
    return make_command(ctype, step_id, 1, "target", validation_strategy="DOM_PRESENCE")


class TestAbstractAdapter:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ExecutionAdapter()
    def test_routing_table_complete(self):
        for ct in CommandType:
            assert ct in ExecutionAdapter.COMMAND_ROUTING
    def test_nine_operations(self):
        assert len(ADAPTER_OPERATIONS) == 9


class TestMockAdapter:
    def test_name(self):
        assert MockBrowserAdapter().name == "mock"
    def test_navigate_success(self):
        r = MockBrowserAdapter().navigate(_cmd(CommandType.navigate))
        assert r.success is True
        assert r.validation_passed is True
    def test_all_operations_success(self):
        a = MockBrowserAdapter()
        for ct, method in [(CommandType.navigate, a.navigate), (CommandType.click, a.click),
                           (CommandType.type, a.type), (CommandType.wait, a.wait),
                           (CommandType.extract, a.extract), (CommandType.validate, a.validate),
                           (CommandType.upload, a.upload), (CommandType.download, a.download),
                           (CommandType.custom, a.execute_custom)]:
            r = method(_cmd(ct))
            assert r.success is True
    def test_duration_matches_profile(self):
        r = MockBrowserAdapter().navigate(_cmd(CommandType.navigate))
        assert r.duration_ms == SIMULATED_DURATION_MS[CommandType.navigate]
    def test_logs_present(self):
        r = MockBrowserAdapter().click(_cmd(CommandType.click))
        assert len(r.logs) >= 1
    def test_output_simulated(self):
        r = MockBrowserAdapter().navigate(_cmd())
        assert r.output["simulated"] is True
    def test_dispatch_routes(self):
        a = MockBrowserAdapter()
        r = a.dispatch(_cmd(CommandType.extract))
        assert r.success is True
    def test_records_dispatched(self):
        a = MockBrowserAdapter()
        c = _cmd()
        a.dispatch(c)
        assert c.command_id in a.dispatched


class TestMockAdapterFailures:
    def test_failure_step(self):
        a = MockBrowserAdapter(failure_steps={"step-bad"})
        r = a.navigate(_cmd(step_id="step-bad"))
        assert r.success is False
    def test_validation_fail_step(self):
        a = MockBrowserAdapter(validation_fail_steps={"step-v"})
        r = a.extract(_cmd(CommandType.extract, step_id="step-v"))
        assert r.success is True
        assert r.validation_passed is False
    def test_flaky_step_first_fails_then_succeeds(self):
        a = MockBrowserAdapter(flaky_steps={"step-f"})
        r1 = a.navigate(_cmd(step_id="step-f"))
        r2 = a.navigate(_cmd(step_id="step-f"))
        assert r1.success is False
        assert r2.success is True
    def test_deterministic_other_steps_ok(self):
        a = MockBrowserAdapter(failure_steps={"step-bad"})
        assert a.navigate(_cmd(step_id="step-ok")).success is True
    def test_reset(self):
        a = MockBrowserAdapter(flaky_steps={"step-f"})
        a.navigate(_cmd(step_id="step-f"))
        a.reset()
        # after reset, the flaky counter restarts → first attempt fails again
        assert a.navigate(_cmd(step_id="step-f")).success is False


class TestFutureAdapters:
    @pytest.mark.parametrize("cls,name", [
        (PlaywrightAdapter, "playwright"),
        (ChromeCDPAdapter, "chrome_cdp"),
        (NativeChromeExtensionAdapter, "native_chrome_extension"),
        (VisionAdapter, "vision"),
    ])
    def test_name(self, cls, name):
        assert cls().name == name

    @pytest.mark.parametrize("cls", [PlaywrightAdapter, ChromeCDPAdapter,
                                     NativeChromeExtensionAdapter, VisionAdapter])
    def test_navigate_not_implemented(self, cls):
        with pytest.raises(NotImplementedError):
            cls().navigate(_cmd())

    @pytest.mark.parametrize("cls", [PlaywrightAdapter, ChromeCDPAdapter,
                                     NativeChromeExtensionAdapter, VisionAdapter])
    def test_all_ops_not_implemented(self, cls):
        a = cls()
        for method in [a.navigate, a.click, a.type, a.wait, a.extract,
                       a.validate, a.upload, a.download, a.execute_custom]:
            with pytest.raises(NotImplementedError):
                method(_cmd())

    def test_future_registry(self):
        assert len(FUTURE_ADAPTERS) == 4
        assert "playwright" in FUTURE_ADAPTERS
        assert "vision" in FUTURE_ADAPTERS
