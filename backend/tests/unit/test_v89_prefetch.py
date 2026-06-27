"""V8.9 Browser Runtime Layer — Unit tests: prefetch.py (PredictivePrefetch)."""
import pytest
from app.runtime import prefetch
from app.runtime.models import (
    ContextSnapshot, PrefetchType, RuntimeEventType, make_runtime_event, make_session,
)


def _ev(et, now=1.0):
    return make_runtime_event(et, "rt-1", now=now)


def _snap(read_view="", title="", url="http://x"):
    return ContextSnapshot(last_read_view=read_view, last_title=title, last_url=url)


class TestCompare:
    def test_two_url_changes_compare(self):
        evs = [_ev(RuntimeEventType.url_changed), _ev(RuntimeEventType.url_changed)]
        h = prefetch.predict(None, evs, _snap())
        assert h.prefetch_type == PrefetchType.compare

    def test_two_tab_switches_compare(self):
        evs = [_ev(RuntimeEventType.tab_switched), _ev(RuntimeEventType.tab_switched)]
        h = prefetch.predict(None, evs, _snap())
        assert h.prefetch_type == PrefetchType.compare

    def test_compare_title_keyword(self):
        h = prefetch.predict(None, [], _snap(title="iPhone vs Android"))
        assert h.prefetch_type == PrefetchType.compare

    def test_compare_keyword_review(self):
        h = prefetch.predict(None, [], _snap(title="Best Laptop Review 2026"))
        assert h.prefetch_type == PrefetchType.compare

    def test_compare_actionable(self):
        evs = [_ev(RuntimeEventType.url_changed), _ev(RuntimeEventType.url_changed)]
        assert prefetch.predict(None, evs, _snap()).is_actionable

    def test_compare_high_confidence_when_both(self):
        evs = [_ev(RuntimeEventType.url_changed), _ev(RuntimeEventType.url_changed)]
        h = prefetch.predict(None, evs, _snap(title="A vs B"))
        assert h.confidence == 0.8


class TestQA:
    def test_three_selections_qa(self):
        evs = [_ev(RuntimeEventType.selection_changed) for _ in range(3)]
        h = prefetch.predict(None, evs, _snap())
        assert h.prefetch_type == PrefetchType.qa

    def test_two_selections_not_qa(self):
        evs = [_ev(RuntimeEventType.selection_changed) for _ in range(2)]
        h = prefetch.predict(None, evs, _snap())
        assert h.prefetch_type != PrefetchType.qa

    def test_qa_actionable(self):
        evs = [_ev(RuntimeEventType.selection_changed) for _ in range(3)]
        assert prefetch.predict(None, evs, _snap()).is_actionable


class TestSummarize:
    def test_long_article_summarize(self):
        h = prefetch.predict(None, [], _snap(read_view="x" * 3000))
        assert h.prefetch_type == PrefetchType.summarize

    def test_short_article_not_summarize(self):
        h = prefetch.predict(None, [], _snap(read_view="x" * 100))
        assert h.prefetch_type != PrefetchType.summarize

    def test_long_article_with_nav_not_summarize(self):
        # navigation present → compare wins, not summarize
        evs = [_ev(RuntimeEventType.url_changed), _ev(RuntimeEventType.url_changed)]
        h = prefetch.predict(None, evs, _snap(read_view="x" * 3000))
        assert h.prefetch_type == PrefetchType.compare


class TestNone:
    def test_no_signal_none(self):
        h = prefetch.predict(None, [], _snap(read_view="short"))
        assert h.prefetch_type == PrefetchType.none

    def test_none_not_actionable(self):
        h = prefetch.predict(None, [], _snap(read_view="short"))
        assert not h.is_actionable

    def test_none_zero_confidence(self):
        h = prefetch.predict(None, [], _snap(read_view="short"))
        assert h.confidence == 0.0


class TestSignalsAndDict:
    def test_signals_present(self):
        evs = [_ev(RuntimeEventType.selection_changed) for _ in range(3)]
        h = prefetch.predict(None, evs, _snap())
        assert "selection_changes" in h.signals
        assert h.signals["selection_changes"] == 3

    def test_to_dict_keys(self):
        d = prefetch.predict(None, [], _snap()).to_dict()
        for k in ["prefetch_type", "reason", "confidence", "is_actionable", "signals"]:
            assert k in d

    def test_read_view_chars_signal(self):
        h = prefetch.predict(None, [], _snap(read_view="x" * 500))
        assert h.signals["read_view_chars"] == 500

    def test_priority_compare_over_qa(self):
        # both compare (2 url) and qa (3 selections) → compare wins (evaluated first)
        evs = ([_ev(RuntimeEventType.url_changed)] * 2 +
               [_ev(RuntimeEventType.selection_changed)] * 3)
        h = prefetch.predict(None, evs, _snap())
        assert h.prefetch_type == PrefetchType.compare
