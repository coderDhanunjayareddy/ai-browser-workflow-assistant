"""M0.6 unit tests — trace schema + recorder (offline, with test doubles)."""
import json
import os

from benchmark.trace import schema
from benchmark.trace.recorder import TraceRecorder
from benchmark.trace.tracing_client import Exchange
from benchmark.analyze_client import AnalyzeResult, SuggestedActionDTO
from benchmark.m0_models import M0TaskResult, M0StepRecord, TaskStatus


def _result():
    r = M0TaskResult(task_id="fixture__login_form", website="Fixture", difficulty="simple",
                     category="FORM_SUBMIT", executor_mode="playwright", status=TaskStatus.stuck)
    r.failure_category = "PLANNING"
    r.failure_detail = "no progress across repeated identical steps"
    r.steps = [
        M0StepRecord(0, action_type="fill", action_selector="#u", action_value="tester",
                     executed=True, execution_success=True, locator_strategy="css_selector",
                     locator_attempts=1, validation_passed=False,
                     validation_detail="exec=True dom_changed=False", execute_ms=42.0,
                     url_after="http://127.0.0.1/login"),
        M0StepRecord(1, action_type="fill", action_selector="#u", action_value="tester",
                     executed=True, execution_success=True, locator_strategy="css_selector",
                     locator_attempts=1, validation_passed=False,
                     validation_detail="exec=True dom_changed=False", execute_ms=40.0,
                     url_after="http://127.0.0.1/login"),
    ]
    return r


def _exchanges(session):
    def ex(i):
        act = SuggestedActionDTO(action_id=f"a{i}", action_type="fill", target_selector="#u",
                                 value="tester", description="fill username",
                                 reasoning="fill the username field", confidence=0.9,
                                 safety_level="safe")
        res = AnalyzeResult(analysis="I will fill the username", suggested_actions=[act],
                            prompt_tokens=1200, completion_tokens=150)
        return Exchange(trace_id=f"tid{i}", session_id=session, task="log in",
                        page_context={"url": "http://127.0.0.1/login", "title": "Login",
                                      "visible_text": "Login form here",
                                      "interactive_elements": [{"selector": "#u", "text": "", "role": "textbox"}]},
                        prior_steps=[], timestamp=1000.0 + i, result=res)
    return [ex(0), ex(1)]


def test_schema_builders_shape():
    t = schema.step_trace(
        trace_id="x", run_id="r", task_id="t", session_id="s", step_index=0,
        observation=schema.observation(url="u", title="ti", dom_snapshot=None, screenshot_before=None,
                                       screenshot_after=None, visible_text_summary="", interactive_element_count=0,
                                       elements_summary=[]),
        planner_input=schema.planner_input(task="t", page_context_sent={}, prior_steps_sent=[],
                                           compressed_context=None, system_prompt_version=None, model=None, timestamp=0.0),
        provider_request=schema.provider_request(None),
        provider_response=schema.provider_response(None, parsed={}, parse_error=None),
        parsed_action=schema.parsed_action(analysis="", action_type=None, target=None, value=None,
                                           reasoning=None, confidence=None, clarification=None),
        executor=schema.executor(locator_strategy=None, selector_used=None, locator_attempts=0,
                                 start_ms=0, end_ms=0, duration_ms=0, result="failed", browser_error=None),
        validation=schema.validation(validation_type="x", passed=None, reason="", dom_changed=None,
                                     url_changed=None, success_criteria_satisfied=False),
        loop_decision=schema.loop_decision(decision="continue", reason=""))
    assert t["schema_version"] == "planner_trace_v1"
    assert t["provider_request"]["available"] is False  # backend off


def test_recorder_merges_all_sources(tmp_path):
    artifacts = tmp_path / "art"
    out = tmp_path / "out"
    tdir = tmp_path / "trace"
    # a backend side-channel file for step 0's trace_id
    (tdir / "backend").mkdir(parents=True)
    (tdir / "backend" / "tid0.json").write_text(json.dumps({
        "schema_version": "provider_exchange_v1", "trace_id": "tid0", "captured_at": 1.0,
        "request": {"provider": "openrouter", "model": "openai/gpt-4o-mini",
                    "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "COMPRESSED..."}],
                    "temperature": 0, "max_tokens": 512},
        "response": {"raw_text": '{"suggested_actions":[...]}', "finish_reason": "stop",
                     "usage": {"total_tokens": 1350}},
        "latency_ms": 812.0}), encoding="utf-8")

    result = _result()
    session = "benchmark_fixture__login_form_r1"
    rec = TraceRecorder(enabled=True, artifacts_dir=str(artifacts), out_dir=str(out),
                        trace_dir=str(tdir), run_id="r1")
    traces = rec.build_task(result, _exchanges(session))

    assert len(traces) == 2
    t0 = traces[0]
    # backend-sourced exact prompt present for step 0
    assert t0["provider_request"]["available"] is True
    assert t0["provider_request"]["assembled_prompt"][0]["content"] == "SYS"
    assert t0["provider_response"]["raw_text"].startswith("{")
    assert t0["provider_response"]["latency_ms"] == 812.0
    # benchmark-sourced parsed action + reasoning
    assert t0["parsed_action"]["action_type"] == "fill"
    assert t0["parsed_action"]["reasoning"] == "fill the username field"
    assert t0["executor"]["selector_used"] == "#u"
    assert t0["validation"]["dom_changed"] is False
    # step 1 has no backend file → marked unavailable, not fabricated
    assert traces[1]["provider_request"]["available"] is False
    # terminal decision mirrors the STUCK status
    assert traces[1]["loop_decision"]["decision"] == "stuck"
    # files written
    assert (out / "r1" / "fixture__login_form" / "step_000.trace.json").exists()
    assert (out / "r1" / "fixture__login_form" / "index.json").exists()


def test_recorder_disabled_is_noop(tmp_path):
    rec = TraceRecorder(enabled=False, artifacts_dir=str(tmp_path), out_dir=str(tmp_path / "o"),
                        trace_dir=str(tmp_path / "t"), run_id="r")
    assert rec.build_task(_result(), []) == []
    assert not (tmp_path / "o").exists()
