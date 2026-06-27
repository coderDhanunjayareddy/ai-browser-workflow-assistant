"""Phase B Execution Gateway — Unit tests: dispatcher.py."""
import pytest
from app.execution_gateway import dispatcher
from app.execution_gateway.dispatcher import ACTION_TO_COMMAND
from app.execution_gateway.models import CommandType
from app.execution_gateway.mock_adapter import MockBrowserAdapter
from app.execution_planning.models import ActionType, TargetType, ValidationStrategy, make_step


def _step(action=ActionType.navigate, desc="http://a"):
    return make_step(1, action, TargetType.url, desc, parameters={"url": "http://a"},
                     expected_result="ok")


class TestActionMapping:
    def test_navigate(self):
        assert ACTION_TO_COMMAND[ActionType.navigate] == CommandType.navigate
    def test_read_to_extract(self):
        assert ACTION_TO_COMMAND[ActionType.read] == CommandType.extract
    def test_extract(self):
        assert ACTION_TO_COMMAND[ActionType.extract] == CommandType.extract
    def test_input_to_type(self):
        assert ACTION_TO_COMMAND[ActionType.input] == CommandType.type
    def test_click(self):
        assert ACTION_TO_COMMAND[ActionType.click] == CommandType.click
    def test_scroll_to_custom(self):
        assert ACTION_TO_COMMAND[ActionType.scroll] == CommandType.custom
    def test_wait(self):
        assert ACTION_TO_COMMAND[ActionType.wait] == CommandType.wait
    def test_validate(self):
        assert ACTION_TO_COMMAND[ActionType.validate] == CommandType.validate
    def test_all_actions_mapped(self):
        for at in ActionType:
            assert at in ACTION_TO_COMMAND


class TestToCommand:
    def test_returns_command(self):
        c = dispatcher.to_command(_step())
        assert c.command_type == CommandType.navigate
    def test_step_id_preserved(self):
        s = _step()
        assert dispatcher.to_command(s).step_id == s.step_id
    def test_order_preserved(self):
        assert dispatcher.to_command(_step()).order == 1
    def test_parameters_copied(self):
        c = dispatcher.to_command(_step())
        assert c.parameters == {"url": "http://a"}
    def test_validation_strategy_string(self):
        c = dispatcher.to_command(_step())
        assert c.validation_strategy == ValidationStrategy.url_match.value
    def test_rollback_action_string(self):
        c = dispatcher.to_command(_step())
        assert c.rollback_action == "NAVIGATE_BACK"
    def test_expected_result(self):
        c = dispatcher.to_command(_step())
        assert c.expected_result == "ok"


class TestDispatch:
    def test_dispatch_navigate(self):
        c = dispatcher.to_command(_step(ActionType.navigate))
        r = dispatcher.dispatch(c, MockBrowserAdapter())
        assert r.success is True
    def test_dispatch_extract(self):
        c = dispatcher.to_command(_step(ActionType.extract, "content"))
        r = dispatcher.dispatch(c, MockBrowserAdapter())
        assert r.success is True
    def test_dispatch_routes_to_correct_method(self):
        a = MockBrowserAdapter()
        c = dispatcher.to_command(_step(ActionType.click, "btn"))
        r = dispatcher.dispatch(c, a)
        # click duration is 2.0 in the mock profile
        assert r.duration_ms == 2.0
    def test_dispatch_failure(self):
        s = _step()
        a = MockBrowserAdapter(failure_steps={s.step_id})
        c = dispatcher.to_command(s)
        assert dispatcher.dispatch(c, a).success is False
