"""Phase E — Unit tests: form_intelligence.py + table_intelligence.py."""
import pytest
from app.website_intelligence import dom_snapshot, form_intelligence, table_intelligence


SIGNUP = """
<form id="signup" aria-label="Sign Up">
  <label for="email">Email Address</label>
  <input id="email" name="email" type="email" required autocomplete="email" placeholder="you@x.com"/>
  <label>Password <input name="pw" type="password" required minlength="8"/></label>
  <input name="avatar" type="file"/>
  <input name="dob" type="date"/>
  <fieldset><legend>Preferences</legend>
    <input type="checkbox" name="news"/> <input type="checkbox" name="promo"/>
    <input type="radio" name="plan" value="free"/> <input type="radio" name="plan" value="pro"/>
  </fieldset>
  <select name="country"><option>US</option><option>CA</option></select>
  <button type="submit">Create Account</button>
  <button type="reset">Clear</button>
</form>
"""


def _forms(html):
    return form_intelligence.analyze_forms(dom_snapshot.from_html(html))


class TestFormIntelligence:
    def test_one_form(self):
        assert len(_forms(SIGNUP)) == 1

    def test_form_id_and_label(self):
        f = _forms(SIGNUP)[0]
        assert f.form_id == "signup"
        assert f.label == "Sign Up"

    def test_fields_detected(self):
        f = _forms(SIGNUP)[0]
        names = {fl.name for fl in f.fields}
        assert {"email", "pw", "avatar", "dob", "country"} <= names

    def test_labels(self):
        f = _forms(SIGNUP)[0]
        email = next(fl for fl in f.fields if fl.name == "email")
        assert email.label == "Email Address"
        pw = next(fl for fl in f.fields if fl.name == "pw")
        assert "Password" in pw.label   # wrapping label

    def test_required(self):
        f = _forms(SIGNUP)[0]
        assert f.required_count == 2   # email + pw only
        assert next(fl for fl in f.fields if fl.name == "email").required is True
        assert next(fl for fl in f.fields if fl.name == "avatar").required is False

    def test_password_file_date(self):
        f = _forms(SIGNUP)[0]
        assert f.has_password is True
        assert f.has_file_upload is True
        assert f.has_date_picker is True

    def test_submit_reset(self):
        f = _forms(SIGNUP)[0]
        assert f.submit_label == "Create Account"
        assert f.reset_label == "Clear"

    def test_checkbox_radio_groups(self):
        f = _forms(SIGNUP)[0]
        assert "news" in f.checkbox_groups and "promo" in f.checkbox_groups
        assert "plan" in f.radio_groups

    def test_field_groups(self):
        f = _forms(SIGNUP)[0]
        assert "Preferences" in f.field_groups

    def test_select_options(self):
        f = _forms(SIGNUP)[0]
        country = next(fl for fl in f.fields if fl.name == "country")
        assert country.field_type == "select"
        assert country.options == ["US", "CA"]

    def test_autocomplete(self):
        f = _forms(SIGNUP)[0]
        assert next(fl for fl in f.fields if fl.name == "email").autocomplete == "email"

    def test_validation_hints(self):
        f = _forms(SIGNUP)[0]
        assert any("email" in h.lower() for h in f.validation_hints)
        assert any("length" in h.lower() for h in f.validation_hints)

    def test_field_locators_present(self):
        f = _forms(SIGNUP)[0]
        assert all(fl.locator is not None for fl in f.fields)

    def test_to_dict(self):
        d = _forms(SIGNUP)[0].to_dict()
        for k in ["form_id", "label", "fields", "field_groups", "submit_label", "reset_label",
                  "has_password", "has_file_upload", "has_date_picker", "checkbox_groups",
                  "radio_groups", "required_count", "validation_hints", "field_count", "locator"]:
            assert k in d

    def test_no_forms(self):
        assert _forms("<div>no form here</div>") == []


PRODUCTS = """
<div class="data-table">
  <input type="search" placeholder="filter rows"/>
  <button>Export CSV</button>
  <table id="products"><caption>Product List</caption>
    <thead><tr><th aria-sort="ascending">Name</th><th class="sortable">Price</th><th>Stock</th></tr></thead>
    <tbody>
      <tr><td><input type="checkbox"/></td><td>A</td><td><button>Edit</button><button>Delete</button></td></tr>
      <tr><td><input type="checkbox"/></td><td>B</td><td><button>Edit</button></td></tr>
      <tr><td><input type="checkbox"/></td><td>C</td><td></td></tr>
    </tbody>
  </table>
  <nav class="pagination"><a href="?p=1">1</a><a href="?p=2">2</a></nav>
</div>
"""


def _tables(html):
    return table_intelligence.analyze_tables(dom_snapshot.from_html(html))


class TestTableIntelligence:
    def test_one_table(self):
        assert len(_tables(PRODUCTS)) == 1

    def test_table_id_label(self):
        t = _tables(PRODUCTS)[0]
        assert t.table_id == "products"
        assert t.label == "Product List"

    def test_headers(self):
        t = _tables(PRODUCTS)[0]
        assert t.headers == ["Name", "Price", "Stock"]

    def test_row_count(self):
        assert _tables(PRODUCTS)[0].row_count == 3

    def test_sortable_columns(self):
        t = _tables(PRODUCTS)[0]
        assert "Name" in t.sortable_columns
        assert "Price" in t.sortable_columns
        assert "Stock" not in t.sortable_columns

    def test_pagination(self):
        assert _tables(PRODUCTS)[0].has_pagination is True

    def test_search(self):
        assert _tables(PRODUCTS)[0].has_search is True

    def test_selection(self):
        assert _tables(PRODUCTS)[0].has_selection is True

    def test_action_buttons(self):
        t = _tables(PRODUCTS)[0]
        assert "Edit" in t.action_buttons
        assert "Delete" in t.action_buttons

    def test_export_buttons(self):
        assert any("Export" in b for b in _tables(PRODUCTS)[0].export_buttons)

    def test_columns(self):
        t = _tables(PRODUCTS)[0]
        assert len(t.columns) == 3
        assert t.columns[0].header == "Name"
        assert t.columns[0].sortable is True

    def test_to_dict(self):
        d = _tables(PRODUCTS)[0].to_dict()
        for k in ["table_id", "label", "headers", "columns", "row_count", "column_count",
                  "sortable_columns", "has_pagination", "has_selection", "has_search",
                  "has_filters", "action_buttons", "export_buttons", "locator"]:
            assert k in d

    def test_simple_table_no_widget(self):
        t = _tables("<table><tr><th>X</th></tr><tr><td>1</td></tr></table>")[0]
        assert t.headers == ["X"]
        assert t.row_count == 1
        assert t.has_pagination is False

    def test_no_tables(self):
        assert _tables("<div>none</div>") == []
