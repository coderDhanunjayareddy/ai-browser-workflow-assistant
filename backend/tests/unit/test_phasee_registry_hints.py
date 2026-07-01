"""Phase E — Unit tests: interactive_registry + execution_hints + analyzer + inspector."""
import pytest
from app.website_intelligence import (
    dom_snapshot, interactive_registry, execution_hints, analyzer, inspector,
    semantic_analyzer, form_intelligence, table_intelligence, navigation_intelligence,
    dialog_intelligence,
)
from app.website_intelligence.models import ElementCategory, Priority


PAGE = """
<body>
  <nav aria-label="Primary"><a href="/home" class="active">Home</a><a href="/p">Products</a></nav>
  <form id="login">
    <input id="user" name="user" type="text"/>
    <input name="pw" type="password"/>
    <input name="file" type="file"/>
    <select name="lang"><option>en</option></select>
    <button type="submit" class="primary">Sign In</button>
  </form>
  <a href="/report.pdf" download>Download Report</a>
  <div class="spinner">Loading...</div>
  <div role="dialog" aria-label="Confirm"><button>Yes</button><button>Cancel</button></div>
</body>
"""


def _root():
    return dom_snapshot.from_html(PAGE)


class TestRegistry:
    def test_builds_entries(self):
        reg = interactive_registry.build_registry(_root())
        assert len(reg) >= 7

    def test_unique_ids(self):
        reg = interactive_registry.build_registry(_root())
        ids = [e.semantic_id for e in reg]
        assert len(ids) == len(set(ids))

    def test_categories(self):
        reg = interactive_registry.build_registry(_root())
        cats = {e.category for e in reg}
        assert ElementCategory.button in cats
        assert ElementCategory.link in cats
        assert ElementCategory.form_control in cats
        assert ElementCategory.upload in cats
        assert ElementCategory.download in cats
        assert ElementCategory.selection in cats

    def test_priority_primary_submit(self):
        reg = interactive_registry.build_registry(_root())
        signin = next(e for e in reg if e.label == "Sign In")
        assert signin.priority == Priority.primary

    def test_validation_strategy(self):
        reg = interactive_registry.build_registry(_root())
        link = next(e for e in reg if e.label == "Home")
        assert link.validation_strategy == "URL_MATCH"
        pw = next(e for e in reg if e.role == "textbox" and "pw" in (e.semantic_id or ""))
        assert pw.validation_strategy == "VALUE_EQUALS"
        dl = next(e for e in reg if e.category == ElementCategory.download)
        assert dl.validation_strategy == "FILE_EXISTS"

    def test_visible_enabled(self):
        reg = interactive_registry.build_registry(_root())
        assert all(isinstance(e.visible, bool) and isinstance(e.enabled, bool) for e in reg)

    def test_disabled_detected(self):
        reg = interactive_registry.build_registry(dom_snapshot.from_html("<button disabled>X</button>"))
        assert reg[0].enabled is False

    def test_locators(self):
        reg = interactive_registry.build_registry(_root())
        assert all(e.locator is not None for e in reg)

    def test_to_dict(self):
        d = interactive_registry.build_registry(_root())[0].to_dict()
        for k in ["semantic_id", "role", "category", "priority", "label", "visible",
                  "enabled", "validation_strategy", "locator"]:
            assert k in d


class TestHints:
    def _hints(self):
        root = _root()
        page = semantic_analyzer.analyze_page(root)
        forms = form_intelligence.analyze_forms(root)
        tables = table_intelligence.analyze_tables(root)
        nav = navigation_intelligence.analyze_navigation(root)
        dialogs = dialog_intelligence.analyze_dialogs(root)
        return execution_hints.build_hints(root, page, forms, tables, nav, dialogs)

    def test_loading_indicator(self):
        assert any(h.hint_type == "loading_indicator" for h in self._hints())

    def test_preferred_validation(self):
        assert any(h.hint_type == "preferred_validation" for h in self._hints())

    def test_expected_upload(self):
        assert any(h.hint_type == "expected_upload" for h in self._hints())

    def test_expected_download(self):
        assert any(h.hint_type == "expected_download" for h in self._hints())

    def test_expected_dialog(self):
        assert any(h.hint_type == "expected_dialog" for h in self._hints())

    def test_all_advisory(self):
        assert all(h.advisory is True for h in self._hints())

    def test_to_dict(self):
        d = self._hints()[0].to_dict()
        for k in ["hint_type", "target", "value", "confidence", "advisory"]:
            assert k in d


class TestAnalyzerFacade:
    def test_analyze_html(self):
        r = analyzer.analyze_html(PAGE, url="http://x", title="T")
        assert r.url == "http://x"
        assert r.title == "T"
        assert len(r.forms) == 1
        assert len(r.registry) >= 7
        assert len(r.dialogs) == 1

    def test_stats(self):
        r = analyzer.analyze_html(PAGE)
        for k in ["dom_nodes", "forms", "tables", "dialogs", "interactive_elements", "hints", "type_counts"]:
            assert k in r.stats

    def test_latency_recorded(self):
        assert analyzer.analyze_html(PAGE).latency_ms >= 0.0

    def test_to_dict(self):
        d = analyzer.analyze_html(PAGE).to_dict()
        for k in ["url", "title", "page", "forms", "tables", "navigation", "dialogs",
                  "registry", "hints", "stats", "latency_ms"]:
            assert k in d

    def test_analyze_dict_snapshot(self):
        snap = {"tag": "body", "children": [{"tag": "form", "id": "f", "children": [{"tag": "input", "name": "q"}]}]}
        r = analyzer.analyze(snap)
        assert len(r.forms) == 1

    def test_empty_page(self):
        r = analyzer.analyze_html("<body></body>")
        assert r.forms == [] and r.tables == [] and r.dialogs == []


class TestInspector:
    def test_slices(self):
        r = analyzer.analyze_html(PAGE)
        assert isinstance(inspector.semantic_tree(r), dict)
        assert isinstance(inspector.forms(r), list)
        assert isinstance(inspector.tables(r), list)
        assert isinstance(inspector.dialogs(r), list)
        assert isinstance(inspector.navigation(r), dict)
        assert isinstance(inspector.registry(r), list)
        assert isinstance(inspector.hints(r), list)
        assert isinstance(inspector.locator_metadata(r), list)

    def test_summary(self):
        s = inspector.summary(analyzer.analyze_html(PAGE))
        for k in ["url", "title", "sections", "forms", "tables", "dialogs",
                  "blocking_dialogs", "interactive_elements", "hints", "type_counts", "latency_ms"]:
            assert k in s

    def test_locator_metadata_shape(self):
        lm = inspector.locator_metadata(analyzer.analyze_html(PAGE))
        assert all("semantic_id" in x and "locator" in x for x in lm)
