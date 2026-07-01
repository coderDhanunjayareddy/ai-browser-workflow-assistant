"""Phase E — Regression tests for adversarial-review findings (locked-in fixes)."""
import pytest
from app.website_intelligence import (
    dom_snapshot, locator_builder, semantic_analyzer, form_intelligence,
    table_intelligence, dialog_intelligence,
)
from app.website_intelligence.models import SemanticType


def N(html, tag):
    return dom_snapshot.from_html(html).find_first(lambda n: n.tag == tag)


class TestLocatorEscaping:
    def test_tailwind_class_skipped_in_css(self):
        loc = locator_builder.build_locator(N("<div class='w-1/2 hover:bg-red'>x</div>", "div"))
        # invalid CSS class tokens are skipped → falls back to plain tag (no '.w-1/2')
        assert "/" not in loc.css and ":" not in loc.css
        assert loc.css == "div"

    def test_simple_class_used(self):
        loc = locator_builder.build_locator(N("<div class='card'>x</div>", "div"))
        assert loc.css == "div.card"

    def test_digit_leading_id_uses_attr_selector(self):
        loc = locator_builder.build_locator(N("<div id='123'>x</div>", "div"))
        assert loc.css == 'div[id="123"]'   # not div#123 (invalid)

    def test_xpath_escapes_double_quote(self):
        loc = locator_builder.build_locator(N('<button>Say "hi"</button>', "button"), text='Say "hi"')
        # xpath must be a valid literal (single-quoted since value has double-quotes)
        assert loc.xpath == "//button[normalize-space()='Say \"hi\"']"

    def test_id_xpath_normal(self):
        loc = locator_builder.build_locator(N("<div id='main'>x</div>", "div"))
        assert loc.xpath == '//*[@id="main"]'


class TestPaginationPrecision:
    def test_page_header_not_pagination(self):
        st, _ = semantic_analyzer.classify(N("<nav aria-label='Page header links'><a href='/'>x</a></nav>", "nav"))
        assert st == SemanticType.navigation   # not pagination

    def test_in_page_nav_not_pagination(self):
        st, _ = semantic_analyzer.classify(N("<nav aria-label='In-page navigation'><a href='/'>x</a></nav>", "nav"))
        assert st == SemanticType.navigation

    def test_real_pagination_class(self):
        st, _ = semantic_analyzer.classify(N("<nav class='pagination'><a href='/'>1</a></nav>", "nav"))
        assert st == SemanticType.pagination

    def test_real_pagination_aria(self):
        st, _ = semantic_analyzer.classify(N("<nav aria-label='Pagination'><a href='/'>1</a></nav>", "nav"))
        assert st == SemanticType.pagination


class TestSubmitResetDisambiguation:
    def test_submit_with_clear_label_not_reset(self):
        forms = form_intelligence.analyze_forms(dom_snapshot.from_html(
            "<form><input name='x'/><button type='submit'>Clear cart and checkout</button></form>"))
        assert forms[0].submit_label == "Clear cart and checkout"
        assert forms[0].reset_label is None

    def test_submit_value_reset_password_not_reset(self):
        forms = form_intelligence.analyze_forms(dom_snapshot.from_html(
            "<form><input name='x'/><input type='submit' value='Reset password'/></form>"))
        assert forms[0].submit_label == "Reset password"
        assert forms[0].reset_label is None

    def test_explicit_reset_detected(self):
        forms = form_intelligence.analyze_forms(dom_snapshot.from_html(
            "<form><input name='x'/><button type='reset'>Clear</button><button type='submit'>Go</button></form>"))
        assert forms[0].reset_label == "Clear"
        assert forms[0].submit_label == "Go"

    def test_type_button_clear_is_reset(self):
        forms = form_intelligence.analyze_forms(dom_snapshot.from_html(
            "<form><input name='x'/><button type='button'>Clear filters</button><button type='submit'>Go</button></form>"))
        assert forms[0].reset_label == "Clear filters"


class TestTableScoping:
    def test_sibling_tables_dont_share_controls(self):
        html = """<main>
          <div class='data-table'><table id='a'><tr><th>A</th></tr><tr><td>1</td></tr></table></div>
          <div class='data-table'><table id='b'><tr><th>B</th></tr><tr><td>2</td></tr></table>
            <nav class='pagination'><a href='?p=1'>1</a></nav></div>
        </main>"""
        tables = {t.table_id: t for t in table_intelligence.analyze_tables(dom_snapshot.from_html(html))}
        assert tables["a"].has_pagination is False   # a's widget has no pager
        assert tables["b"].has_pagination is True     # b's widget has the pager

    def test_playlist_class_not_grid_container(self):
        html = "<div class='playlist'><table id='t'><tr><th>X</th></tr><tr><td>1</td></tr></table><nav class='pagination'><a href='/'>1</a></nav></div>"
        # 'playlist' is NOT a grid container → pagination (a sibling of the table inside
        # playlist) is still found because container falls back... ensure no false 'list' match
        t = table_intelligence.analyze_tables(dom_snapshot.from_html(html))[0]
        # container falls back to the table itself (playlist not a grid container) → no pager scoped
        assert t.has_pagination is False

    def test_no_balloon_to_main(self):
        html = "<main><table id='t'><tr><th>X</th></tr><tr><td>1</td></tr></table><nav class='pagination'><a href='/'>1</a></nav></main>"
        # <main> is not a grid container → container = table → pagination (sibling) not attributed
        t = table_intelligence.analyze_tables(dom_snapshot.from_html(html))[0]
        assert t.has_pagination is False

    def test_data_table_wrapper_scopes(self):
        html = "<div class='table-responsive'><table id='t'><tr><th>X</th></tr><tr><td>1</td></tr></table><nav class='pagination'><a href='/'>1</a></nav></div>"
        t = table_intelligence.analyze_tables(dom_snapshot.from_html(html))[0]
        assert t.has_pagination is True   # 'table-responsive' token-matches 'table'

    def test_header_button_not_sortable(self):
        html = "<table><thead><tr><th>Name<button>menu</button></th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>"
        t = table_intelligence.analyze_tables(dom_snapshot.from_html(html))[0]
        assert "Name" not in t.sortable_columns

    def test_sort_button_is_sortable(self):
        html = "<table><thead><tr><th>Name<button aria-label='Sort by name'><i></i></button></th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>"
        t = table_intelligence.analyze_tables(dom_snapshot.from_html(html))[0]
        assert "Name" in t.sortable_columns

    def test_multi_tbody_row_count(self):
        html = "<table><tbody><tr><td>1</td></tr><tr><td>2</td></tr></tbody><tbody><tr><td>3</td></tr></tbody></table>"
        t = table_intelligence.analyze_tables(dom_snapshot.from_html(html))[0]
        assert t.row_count == 3

    def test_scope_row_th_not_subtracted(self):
        html = "<table><tr><th scope='row'>R1</th><td>1</td></tr><tr><th scope='row'>R2</th><td>2</td></tr></table>"
        t = table_intelligence.analyze_tables(dom_snapshot.from_html(html))[0]
        assert t.row_count == 2   # no header-only row → none subtracted


class TestDialogPrecision:
    def test_next_button_not_close(self):
        d = dialog_intelligence.analyze_dialogs(dom_snapshot.from_html(
            "<div role='dialog' aria-modal='true'><button>Next</button><button>Exit</button></div>"))[0]
        # neither Next nor Exit is a close affordance; modal w/o cancel → not dismissible via 'x'
        # (Exit isn't a recognized close/cancel word) → dismissible stays False
        assert d.dismissible is False

    def test_x_button_is_close(self):
        d = dialog_intelligence.analyze_dialogs(dom_snapshot.from_html(
            "<div role='dialog' aria-modal='true'><button>x</button><button>Save</button></div>"))[0]
        assert d.dismissible is True

    def test_close_button_is_close(self):
        d = dialog_intelligence.analyze_dialogs(dom_snapshot.from_html(
            "<div role='dialog'><button>Close</button></div>"))[0]
        assert d.dismissible is True

    def test_aria_labelledby_not_used_as_text(self):
        d = dialog_intelligence.analyze_dialogs(dom_snapshot.from_html(
            "<div role='dialog' aria-labelledby='dlg-title-1'><h2>Real Title</h2><button>OK</button></div>"))[0]
        assert d.label == "Real Title"          # heading, not the ID reference
        assert "dlg-title-1" != d.label
