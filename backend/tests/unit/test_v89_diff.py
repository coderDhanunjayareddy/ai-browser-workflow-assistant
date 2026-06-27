"""V8.9 Browser Runtime Layer — Unit tests: diff.py (ContextDiffEngine)."""
import pytest
from app.runtime import diff
from app.runtime.models import ContextSnapshot


def _snap(**kw):
    return ContextSnapshot(**kw)


class TestNoPrior:
    def test_all_fields_added_when_no_old(self):
        new = _snap(last_url="u", last_title="t")
        d = diff.compute(None, new)
        assert "last_url" in d.added
        assert "last_title" in d.added

    def test_none_fields_not_added(self):
        new = _snap(last_url="u")
        d = diff.compute(None, new)
        assert "last_title" not in d.added

    def test_empty_new_no_changes(self):
        assert not diff.compute(None, _snap()).has_changes


class TestAdded:
    def test_field_added(self):
        old = _snap(last_url="u")
        new = _snap(last_url="u", last_title="t")
        d = diff.compute(old, new)
        assert d.added == {"last_title": "t"}

    def test_added_not_in_modified(self):
        old = _snap()
        new = _snap(last_selection="sel")
        d = diff.compute(old, new)
        assert "last_selection" in d.added
        assert "last_selection" not in d.modified


class TestRemoved:
    def test_field_removed(self):
        old = _snap(last_url="u", last_title="t")
        new = _snap(last_url="u")
        d = diff.compute(old, new)
        assert d.removed == {"last_title": "t"}

    def test_removed_carries_old_value(self):
        old = _snap(last_selection="hello")
        new = _snap()
        d = diff.compute(old, new)
        assert d.removed["last_selection"] == "hello"


class TestModified:
    def test_field_modified(self):
        old = _snap(last_url="a")
        new = _snap(last_url="b")
        d = diff.compute(old, new)
        assert d.modified == {"last_url": "b"}

    def test_unchanged_ignored(self):
        old = _snap(last_url="a", last_title="t")
        new = _snap(last_url="a", last_title="t")
        d = diff.compute(old, new)
        assert not d.has_changes

    def test_scroll_position_modified(self):
        old = _snap(last_scroll_position=0)
        new = _snap(last_scroll_position=500)
        d = diff.compute(old, new)
        assert d.modified["last_scroll_position"] == 500

    def test_scroll_zero_not_added_when_same(self):
        old = _snap(last_scroll_position=0)
        new = _snap(last_scroll_position=0)
        assert not diff.compute(old, new).has_changes


class TestDiffRatio:
    def test_ratio_one_field(self):
        old = _snap(last_url="a")
        new = _snap(last_url="b")
        assert diff.compute(old, new).diff_ratio == round(1 / 6, 4)

    def test_ratio_three_fields(self):
        old = _snap()
        new = _snap(last_url="u", last_title="t", last_selection="s")
        assert diff.compute(old, new).diff_ratio == round(3 / 6, 4)

    def test_ratio_all_six(self):
        new = _snap(last_read_view="r", last_dom_summary="d", last_selection="s",
                    last_url="u", last_title="t", last_scroll_position=1)
        assert diff.compute(None, new).diff_ratio == 1.0

    def test_ratio_zero_when_no_change(self):
        old = _snap(last_url="a")
        new = _snap(last_url="a")
        assert diff.compute(old, new).diff_ratio == 0.0


class TestMixed:
    def test_added_removed_modified_together(self):
        old = _snap(last_url="a", last_title="t")          # title will be removed
        new = _snap(last_url="b", last_selection="s")      # url modified, selection added
        d = diff.compute(old, new)
        assert d.modified == {"last_url": "b"}
        assert d.added == {"last_selection": "s"}
        assert d.removed == {"last_title": "t"}
        assert d.changed_field_count == 3

    def test_to_dict_roundtrip(self):
        old = _snap(last_url="a")
        new = _snap(last_url="b")
        d = diff.compute(old, new).to_dict()
        assert d["has_changes"] is True
        assert d["changed_field_count"] == 1
