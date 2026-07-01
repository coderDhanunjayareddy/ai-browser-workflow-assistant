"""M0.6 — backend trace sink is a no-op when TRACE_MODE is off; writes exactly when on."""
import os

from app.core.config import settings
from app.diagnostics import trace_sink


def test_sink_noop_when_trace_mode_off(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "trace_mode", False)
    monkeypatch.setattr(settings, "trace_dir", str(tmp_path))
    # even with a trace_id, nothing is written when disabled
    trace_sink.record_provider_exchange(request={"model": "m"}, response={"raw_text": "x"},
                                        latency_ms=1.0, trace_id="tid")
    assert not (tmp_path / "backend").exists()


def test_sink_writes_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "trace_mode", True)
    monkeypatch.setattr(settings, "trace_dir", str(tmp_path))
    trace_sink.record_provider_exchange(
        request={"provider": "openrouter", "model": "openai/gpt-4o-mini", "messages": [{"a": 1}]},
        response={"raw_text": "{}", "finish_reason": "stop", "usage": {"total_tokens": 5}},
        latency_ms=12.3, trace_id="tid-xyz")
    f = tmp_path / "backend" / "tid-xyz.json"
    assert f.exists()
    import json
    rec = json.loads(f.read_text(encoding="utf-8"))
    assert rec["trace_id"] == "tid-xyz"
    assert rec["request"]["model"] == "openai/gpt-4o-mini"
    assert rec["response"]["raw_text"] == "{}"
    assert rec["latency_ms"] == 12.3


def test_sink_enabled_but_no_trace_id_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "trace_mode", True)
    monkeypatch.setattr(settings, "trace_dir", str(tmp_path))
    trace_sink.set_current(None)
    trace_sink.record_provider_exchange(request={}, response={}, latency_ms=0.0, trace_id=None)
    assert not (tmp_path / "backend").exists() or not os.listdir(tmp_path / "backend")
