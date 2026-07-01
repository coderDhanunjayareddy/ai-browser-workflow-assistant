"""M0.6 unit tests — HTML viewer, tracing-client delegation, and disabled/off no-op."""
import sys
import types

from benchmark.trace.recorder import TraceRecorder
from benchmark.trace.viewer import generate_viewer
from benchmark.trace.tracing_client import TracingAnalyzeClient
from benchmark.analyze_client import AnalyzeClient, AnalyzeResult, SuggestedActionDTO
from benchmark.m0_models import M0TaskResult, M0StepRecord, TaskStatus
from benchmark.trace.tracing_client import Exchange


def _build_one(tmp_path):
    r = M0TaskResult(task_id="t", website="W", difficulty="simple", category="SEARCH",
                     executor_mode="playwright", status=TaskStatus.completed)
    r.steps = [M0StepRecord(0, action_type="click", action_selector="#go", executed=True,
                            execution_success=True, locator_strategy="css_selector",
                            validation_passed=True, validation_detail="exec=True dom_changed=True",
                            url_after="http://x/ok")]
    act = SuggestedActionDTO("a0", "click", "#go", None, "click go", "because", 0.8, "safe")
    ex = Exchange("tid0", "benchmark_t_r", "task", {"url": "http://x", "title": "X",
                  "visible_text": "hello", "interactive_elements": [{"selector": "#go"}]}, [], 1.0,
                  result=AnalyzeResult(analysis="a", suggested_actions=[act]))
    rec = TraceRecorder(enabled=True, artifacts_dir=str(tmp_path), out_dir=str(tmp_path / "out"),
                        trace_dir=str(tmp_path / "trace"), run_id="r")
    rec.build_task(r, [ex])
    return str(tmp_path / "out")


def test_viewer_is_self_contained(tmp_path):
    out = _build_one(tmp_path)
    path = generate_viewer(out_dir=out, run_id="r", task_id="t", artifacts_dir=str(tmp_path))
    assert path is not None
    html = open(path, encoding="utf-8").read()
    assert "window.__TRACES__" in html
    assert "<style>" in html and "<script>" in html
    assert 'src="http' not in html and 'href="http' not in html   # no external assets
    assert "Assembled prompt" in html and "Loop decision" in html


class _FakeInner:
    def __init__(self):
        self.calls = []

    def analyze(self, *, session_id, task, page_context, prior_steps, trace_id=None):
        self.calls.append({"session_id": session_id, "trace_id": trace_id})
        return AnalyzeResult(analysis="ok", suggested_actions=[])


def test_tracing_client_delegates_and_forwards_trace_id():
    inner = _FakeInner()
    tc = TracingAnalyzeClient(inner)
    res = tc.analyze(session_id="s1", task="t", page_context={"url": "u"}, prior_steps=[])
    assert isinstance(res, AnalyzeResult)
    # a trace_id was minted and forwarded to the inner client
    assert inner.calls[0]["trace_id"] is not None
    assert len(inner.calls[0]["trace_id"]) >= 8
    # the exchange was logged and is queryable by session
    assert len(tc.exchanges_for("s1")) == 1


def test_analyze_client_header_only_when_trace_id(monkeypatch):
    # inject a fake requests module so we can inspect the outgoing headers offline
    captured = {}

    class _Resp:
        status_code = 200
        def json(self):
            return {"analysis": "x", "suggested_actions": []}

    fake = types.ModuleType("requests")
    fake.exceptions = types.SimpleNamespace(RequestException=Exception)
    def _post(url, json=None, timeout=None, headers=None):
        captured["headers"] = headers
        return _Resp()
    fake.post = _post
    monkeypatch.setitem(sys.modules, "requests", fake)

    c = AnalyzeClient("http://localhost:8000")
    c.analyze(session_id="s", task="t", page_context={}, prior_steps=[])
    assert captured["headers"] is None                     # normal run: no header
    c.analyze(session_id="s", task="t", page_context={}, prior_steps=[], trace_id="abc123")
    assert captured["headers"] == {"X-Trace-Id": "abc123"}  # traced run: header present
