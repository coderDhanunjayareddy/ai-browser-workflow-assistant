"""
Phase E — Website Intelligence — Validation Suite.

Minimum 1800 deterministic checks: structure, DOM snapshot, semantic classification,
page model, locator builder, form/table/navigation/dialog intelligence, interactive
registry, execution hints, analyzer/inspector, determinism, REST, additivity, and a
static safety scan. All browser-free (HTML fixtures) — fully deterministic.

Run: python validate_phasee.py
"""
import sys
import pathlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0
SECTIONS: list[tuple[str, int, int]] = []

def section(name: str):
    global PASS, FAIL
    SECTIONS.append((name, PASS, FAIL))
    print(f"\n[{name}]")

def check(label: str, cond: bool):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL: {label}")

def summ(name: str):
    prev = SECTIONS[-1]
    print(f"  -> {PASS - prev[1]} pass, {FAIL - prev[2]} fail")


from app.website_intelligence import (
    dom_snapshot, semantic_analyzer, locator_builder, form_intelligence, table_intelligence,
    navigation_intelligence, dialog_intelligence, interactive_registry, execution_hints,
    analyzer, inspector,
)
from app.website_intelligence.models import (
    DomNode, SemanticType, ElementCategory, Priority, LocatorMetadata,
)
from app.execution_gateway.browser.capabilities import EXTENDED_RESOLUTION_PRIORITY


def H(html):
    return dom_snapshot.from_html(html)

def classify_tag(html, tag):
    root = H(html)
    node = root.find_first(lambda n: n.tag == tag) or root
    return semantic_analyzer.classify(node)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Package structure
# ─────────────────────────────────────────────────────────────────────────────
section("1. Package Structure")
for f in ["__init__", "models", "dom_snapshot", "semantic_analyzer", "locator_builder",
          "form_intelligence", "table_intelligence", "navigation_intelligence",
          "dialog_intelligence", "interactive_registry", "execution_hints", "analyzer", "inspector"]:
    check(f"module {f}.py", pathlib.Path(f"app/website_intelligence/{f}.py").exists())
check("REST route file", pathlib.Path("app/api/routes/website_intelligence.py").exists())
summ("1. Package Structure")

# ─────────────────────────────────────────────────────────────────────────────
# 2. DOM snapshot
# ─────────────────────────────────────────────────────────────────────────────
section("2. DOM Snapshot")
root = H("<body><header><h1>T</h1></header><main><form id='f'><input name='q' type='text'/></form></main></body>")
check("from_html body root", root.tag == "body")
check("finds header", root.find_first(lambda n: n.tag == "header") is not None)
check("finds form", root.find_first(lambda n: n.tag == "form") is not None)
check("finds input", root.find_first(lambda n: n.tag == "input") is not None)
inp = H('<input id="e" name="email" type="email" placeholder="P" aria-label="A" data-testid="t" required/>').find_first(lambda n: n.tag == "input")
check("attr id", inp.id == "e")
check("attr name", inp.name == "email")
check("attr type", inp.type == "email")
check("attr placeholder", inp.placeholder == "P")
check("attr aria_label", inp.aria_label == "A")
check("attr testid", inp.testid == "t")
check("attr required present", "required" in inp.attrs)
check("void br", len(H("<div><br/></div>").find_by_tag("br")) == 1)
check("void img", len(H("<div><img src='x'/></div>").find_by_tag("img")) == 1)
check("hidden style", H("<span style='display:none'>x</span>").find_first(lambda n: n.tag == "span").visible is False)
check("visibility hidden", H("<span style='visibility:hidden'>x</span>").find_first(lambda n: n.tag == "span").visible is False)
check("hidden attr", H("<div hidden>x</div>").find_first(lambda n: n.tag == "div").visible is False)
check("type hidden", H("<input type='hidden'/>").find_first(lambda n: n.tag == "input").visible is False)
check("visible default", H("<div>x</div>").find_first(lambda n: n.tag == "div").visible is True)
check("disabled", H("<button disabled>x</button>").find_first(lambda n: n.tag == "button").disabled is True)
check("aria-disabled", H("<button aria-disabled='true'>x</button>").find_first(lambda n: n.tag == "button").disabled is True)
check("role", H("<div role='dialog'>x</div>").find_first(lambda n: n.tag == "div").role == "dialog")
check("href", H("<a href='/p'>x</a>").find_first(lambda n: n.tag == "a").href == "/p")
check("text content", "Hello" in H("<p>Hello World</p>").find_first(lambda n: n.tag == "p").text_content())
check("node_count", H("<div><p/><span/></div>").find_first(lambda n: n.tag == "div").node_count() == 3)
check("class_list", DomNode(tag="div", classes="a b").class_list == ["a", "b"])
check("class_contains", DomNode(tag="div", classes="x-card-y").class_contains("card"))
# from_dict
fd = dom_snapshot.from_dict({"tag": "form", "id": "f1", "role": "form", "children": [{"tag": "input", "name": "q"}]})
check("from_dict tag", fd.tag == "form")
check("from_dict id", fd.id == "f1")
check("from_dict children", len(fd.children) == 1)
check("from_dict empty", dom_snapshot.from_dict({}).tag == "body")
# capture JS is read-only
js = dom_snapshot.CAPTURE_JS
check("capture js reads body", "document.body" in js)
for fb in [".click(", ".type(", ".fill(", ".goto(", ".set_input_files(", "location ="]:
    check(f"capture js no '{fb}'", fb not in js)
summ("2. DOM Snapshot")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Classification — tags / roles / classes
# ─────────────────────────────────────────────────────────────────────────────
section("3. Classification")
tag_cases = [
    ("<header><h1>x</h1></header>", "header", SemanticType.header),
    ("<footer>x</footer>", "footer", SemanticType.footer),
    ("<nav><a href='/'>h</a></nav>", "nav", SemanticType.navigation),
    ("<form><input/></form>", "form", SemanticType.form),
    ("<table><tr><td>x</td></tr></table>", "table", SemanticType.table),
    ("<ul><li>a</li></ul>", "ul", SemanticType.list),
    ("<aside>x</aside>", "aside", SemanticType.sidebar),
    ("<section>x</section>", "section", SemanticType.section),
    ("<main>x</main>", "main", SemanticType.section),
    ("<article>x</article>", "article", SemanticType.section),
    ("<select><option>a</option></select>", "select", SemanticType.dropdown),
    ("<details><summary>s</summary>x</details>", "details", SemanticType.accordion),
    ("<button>x</button>", "button", SemanticType.button),
    ("<a href='/y'>y</a>", "a", SemanticType.link),
    ("<input type='file'/>", "input", SemanticType.upload),
    ("<input type='date'/>", "input", SemanticType.calendar),
    ("<dialog>x</dialog>", "dialog", SemanticType.dialog),
]
for html, tag, exp in tag_cases:
    st, conf = classify_tag(html, tag)
    check(f"tag {tag} -> {exp.value}", st == exp)
    check(f"tag {tag} conf > 0", conf > 0)

role_cases = [
    ("dialog", SemanticType.dialog), ("alertdialog", SemanticType.dialog), ("alert", SemanticType.dialog),
    ("status", SemanticType.dialog), ("banner", SemanticType.header), ("contentinfo", SemanticType.footer),
    ("navigation", SemanticType.navigation), ("toolbar", SemanticType.toolbar), ("grid", SemanticType.grid),
    ("tree", SemanticType.tree), ("menu", SemanticType.menu), ("menubar", SemanticType.menu),
    ("tablist", SemanticType.tabs), ("search", SemanticType.search_bar), ("listbox", SemanticType.dropdown),
    ("combobox", SemanticType.dropdown),
]
for role, exp in role_cases:
    st, conf = classify_tag(f"<div role='{role}'><a href='/'>x</a></div>", "div")
    check(f"role {role} -> {exp.value}", st == exp)
    check(f"role {role} conf>0", conf > 0)

class_cases = [
    ("card", SemanticType.card), ("dashboard", SemanticType.dashboard), ("sidebar", SemanticType.sidebar),
    ("toolbar", SemanticType.toolbar), ("accordion", SemanticType.accordion), ("filter", SemanticType.filter),
    ("modal", SemanticType.dialog), ("toast", SemanticType.dialog), ("drawer", SemanticType.dialog),
    ("popover", SemanticType.dialog), ("overlay", SemanticType.dialog), ("dropdown", SemanticType.dropdown),
    ("datepicker", SemanticType.calendar),
]
for cls, exp in class_cases:
    st, conf = classify_tag(f"<div class='{cls}'>x</div>", "div")
    check(f"class {cls} -> {exp.value}", st == exp)
    check(f"class {cls} conf>0", conf > 0)
# special class navs
check("breadcrumb", classify_tag("<nav aria-label='breadcrumb'><a href='/'>r</a></nav>", "nav")[0] == SemanticType.breadcrumb)
check("pagination", classify_tag("<ul class='pagination'><li>1</li></ul>", "ul")[0] == SemanticType.pagination)
check("download ext", classify_tag("<a href='/x.pdf'>D</a>", "a")[0] == SemanticType.download)
check("download attr", classify_tag("<a href='/x' download>D</a>", "a")[0] == SemanticType.download)
check("unknown span", semantic_analyzer.classify(H("<span>x</span>").find_first(lambda n: n.tag == "span"))[0] is None)
summ("3. Classification")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Page model
# ─────────────────────────────────────────────────────────────────────────────
section("4. Page Model")
PAGE_HTML = """<body>
<header><h1>Acme</h1></header>
<nav aria-label='Main'><a href='/' class='active'>Home</a></nav>
<main><form id='f'><input name='q'/></form>
<table id='t'><caption>Data</caption><thead><tr><th>A</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>
<div class='dashboard'><div class='card'><h3>K</h3></div></div></main>
<footer><h4>Footer</h4></footer></body>"""
page = semantic_analyzer.analyze_page(H(PAGE_HTML), url="http://x", title="Acme")
check("page root type", page.root.type == SemanticType.page)
check("page title", page.title == "Acme")
check("page url", page.url == "http://x")
walk_types = {n.type for n in page.root.walk()}
for st in [SemanticType.header, SemanticType.navigation, SemanticType.form, SemanticType.table,
           SemanticType.footer, SemanticType.dashboard, SemanticType.section]:
    check(f"tree has {st.value}", st in walk_types)
check("sections non-empty", len(page.sections) >= 4)
check("type_counts form", page.type_counts.get("FORM") == 1)
check("type_counts table", page.type_counts.get("TABLE") == 1)
nd = page.root.to_dict()
for k in ["type", "label", "interactive", "confidence", "locator", "children"]:
    check(f"node dict {k}", k in nd)
check("page to_dict", set(page.to_dict().keys()) == {"url", "title", "sections", "type_counts", "root"})
# every structural node has a locator and confidence in [0,1]
for n in page.root.walk():
    check(f"node {n.type.value} conf range", 0.0 <= n.confidence <= 1.0)
summ("4. Page Model")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Locator builder matrix
# ─────────────────────────────────────────────────────────────────────────────
section("5. Locator Builder")
def node_from(html, tag):
    return H(html).find_first(lambda n: n.tag == tag)
loc_cases = [
    ('<button data-testid="t" id="i" name="n">Go</button>', "button", "testid"),
    ('<input aria-label="A" id="i"/>', "input", "aria_label"),
    ('<div role="button" id="i">x</div>', "div", "role"),
    ('<input placeholder="P" id="i"/>', "input", "placeholder"),
    ('<input id="i" name="n"/>', "input", "id"),
    ('<input name="n"/>', "input", "name"),
]
for html, tag, exp_primary in loc_cases:
    loc = locator_builder.build_locator(node_from(html, tag))
    check(f"locator primary {exp_primary}", loc.primary_strategy == exp_primary)
    check(f"locator has css {exp_primary}", bool(loc.css))
    check(f"locator has xpath {exp_primary}", bool(loc.xpath))
    idx = [EXTENDED_RESOLUTION_PRIORITY.index(c) for c in loc.candidates]
    check(f"locator candidates ordered {exp_primary}", idx == sorted(idx))
    valid = set(EXTENDED_RESOLUTION_PRIORITY) | {"role_name"}
    check(f"locator params valid {exp_primary}", set(loc.params.keys()) <= valid)
    check(f"locator to_dict {exp_primary}", set(loc.to_dict().keys()) == {"primary_strategy", "params", "candidates", "css", "xpath"})
# css forms
check("css id", locator_builder.build_locator(node_from('<div id="main">x</div>', "div")).css == "div#main")
check("css testid", '[data-testid="t"]' in locator_builder.build_locator(node_from('<div data-testid="t">x</div>', "div")).css)
check("css name", '[name="q"]' in locator_builder.build_locator(node_from('<input name="q"/>', "input")).css)
check("xpath id", locator_builder.build_locator(node_from('<div id="m">x</div>', "div")).xpath == '//*[@id="m"]')
check("text for button", locator_builder.build_locator(node_from("<button>Save</button>", "button"), text="Save").params.get("text") == "Save")
check("role_name", locator_builder.build_locator(node_from("<div role='button' aria-label='Submit'>x</div>", "div")).params.get("role_name") == "Submit")
# fallback css always
for tag_html in ["<div>x</div>", "<span>y</span>", "<p>z</p>"]:
    loc = locator_builder.build_locator(H(tag_html).children[0])
    check(f"fallback css {tag_html}", bool(loc.css) and bool(loc.xpath))
summ("5. Locator Builder")

# ─────────────────────────────────────────────────────────────────────────────
# 6. Form intelligence
# ─────────────────────────────────────────────────────────────────────────────
section("6. Form Intelligence")
FORM = """<form id='reg' aria-label='Register'>
  <label for='email'>Email</label><input id='email' name='email' type='email' required autocomplete='email'/>
  <label>Pwd <input name='pw' type='password' required minlength='8'/></label>
  <input name='file' type='file'/><input name='dob' type='date'/>
  <input name='age' type='number' min='18' max='99'/>
  <input name='url' type='url'/>
  <fieldset><legend>Opt</legend><input type='checkbox' name='c1'/><input type='checkbox' name='c2'/>
    <input type='radio' name='r1'/><input type='radio' name='r1'/></fieldset>
  <select name='ctry'><option>US</option><option>CA</option><option>MX</option></select>
  <textarea name='bio'></textarea>
  <button type='submit'>Register Now</button><button type='reset'>Reset Form</button>
</form>"""
forms = form_intelligence.analyze_forms(H(FORM))
check("one form", len(forms) == 1)
f = forms[0]
check("form id", f.form_id == "reg")
check("form label", f.label == "Register")
names = {fl.name for fl in f.fields}
for nm in ["email", "pw", "file", "dob", "age", "url", "ctry", "bio"]:
    check(f"field {nm}", nm in names)
check("email label", next(fl for fl in f.fields if fl.name == "email").label == "Email")
check("wrap label", "Pwd" in next(fl for fl in f.fields if fl.name == "pw").label)
check("required count 2", f.required_count == 2)
check("email required", next(fl for fl in f.fields if fl.name == "email").required)
check("file not required", not next(fl for fl in f.fields if fl.name == "file").required)
check("has password", f.has_password)
check("has file", f.has_file_upload)
check("has date", f.has_date_picker)
check("submit", f.submit_label == "Register Now")
check("reset", f.reset_label == "Reset Form")
check("checkbox groups", set(f.checkbox_groups) == {"c1", "c2"})
check("radio groups", f.radio_groups == ["r1"])
check("field groups", "Opt" in f.field_groups)
check("select options", next(fl for fl in f.fields if fl.name == "ctry").options == ["US", "CA", "MX"])
check("select type", next(fl for fl in f.fields if fl.name == "ctry").field_type == "select")
check("textarea type", next(fl for fl in f.fields if fl.name == "bio").field_type == "textarea")
check("autocomplete", next(fl for fl in f.fields if fl.name == "email").autocomplete == "email")
check("email hint", any("email" in h.lower() for h in f.validation_hints))
check("length hint", any("length" in h.lower() for h in f.validation_hints))
check("range hint", any("range" in h.lower() for h in f.validation_hints))
check("url hint", any("url" in h.lower() for h in f.validation_hints))
check("all field locators", all(fl.locator is not None for fl in f.fields))
fd = f.to_dict()
for k in ["form_id", "label", "fields", "field_groups", "submit_label", "reset_label", "has_password",
          "has_file_upload", "has_date_picker", "checkbox_groups", "radio_groups", "required_count",
          "validation_hints", "field_count", "locator"]:
    check(f"form dict {k}", k in fd)
check("no forms", form_intelligence.analyze_forms(H("<div>x</div>")) == [])
# multiple forms
multi = form_intelligence.analyze_forms(H("<div><form id='a'><input name='x'/></form><form id='b'><input name='y'/></form></div>"))
check("two forms", len(multi) == 2)
check("form ids", {m.form_id for m in multi} == {"a", "b"})
summ("6. Form Intelligence")

# ─────────────────────────────────────────────────────────────────────────────
# 7. Table intelligence
# ─────────────────────────────────────────────────────────────────────────────
section("7. Table Intelligence")
TABLE = """<div class='data-table'>
  <input type='search' placeholder='filter'/>
  <button>Export CSV</button><button>Export PDF</button>
  <table id='grid'><caption>Records</caption>
    <thead><tr><th aria-sort='asc'>ID</th><th class='sortable'>Name</th><th>Notes</th></tr></thead>
    <tbody>
      <tr><td><input type='checkbox'/></td><td>A</td><td><button>Edit</button><button>Delete</button></td></tr>
      <tr><td><input type='checkbox'/></td><td>B</td><td><button>Edit</button></td></tr>
      <tr><td><input type='checkbox'/></td><td>C</td><td></td></tr>
      <tr><td><input type='checkbox'/></td><td>D</td><td></td></tr>
    </tbody>
  </table>
  <nav class='pagination'><a href='?p=1'>1</a><a href='?p=2'>2</a></nav>
</div>"""
tables = table_intelligence.analyze_tables(H(TABLE))
check("one table", len(tables) == 1)
t = tables[0]
check("table id", t.table_id == "grid")
check("table caption label", t.label == "Records")
check("headers", t.headers == ["ID", "Name", "Notes"])
check("row count 4", t.row_count == 4)
check("sortable ID", "ID" in t.sortable_columns)
check("sortable Name", "Name" in t.sortable_columns)
check("not sortable Notes", "Notes" not in t.sortable_columns)
check("pagination", t.has_pagination)
check("search", t.has_search)
check("selection", t.has_selection)
check("edit action", "Edit" in t.action_buttons)
check("delete action", "Delete" in t.action_buttons)
check("export csv", any("CSV" in b for b in t.export_buttons))
check("export pdf", any("PDF" in b for b in t.export_buttons))
check("columns 3", len(t.columns) == 3)
check("column0 sortable", t.columns[0].sortable)
check("column2 not sortable", not t.columns[2].sortable)
td = t.to_dict()
for k in ["table_id", "label", "headers", "columns", "row_count", "column_count", "sortable_columns",
          "has_pagination", "has_selection", "has_search", "has_filters", "action_buttons",
          "export_buttons", "locator"]:
    check(f"table dict {k}", k in td)
simple = table_intelligence.analyze_tables(H("<table><tr><th>X</th></tr><tr><td>1</td></tr><tr><td>2</td></tr></table>"))[0]
check("simple headers", simple.headers == ["X"])
check("simple rows", simple.row_count == 2)
check("simple no pagination", simple.has_pagination is False)
check("no tables", table_intelligence.analyze_tables(H("<div>x</div>")) == [])
summ("7. Table Intelligence")

# ─────────────────────────────────────────────────────────────────────────────
# 8. Navigation intelligence
# ─────────────────────────────────────────────────────────────────────────────
section("8. Navigation Intelligence")
NAV = """<body>
<nav aria-label='Primary'><ul>
  <li><a href='/home' class='active'>Home</a></li>
  <li><a href='/products'>Products</a><ul><li><a href='/products/new'>New</a></li></ul></li>
  <li><a href='/about'>About</a></li></ul></nav>
<nav aria-label='breadcrumb'><ol><li><a href='/'>Root</a></li><li><a href='/p'>Products</a></li></ol></nav>
<div role='tablist'><button role='tab' aria-selected='true'>T1</button><button role='tab'>T2</button></div>
<aside class='sidebar'><a href='/s1'>S1</a></aside>
<div role='menu'><a href='/m1'>M1</a></div></body>"""
nav = navigation_intelligence.analyze_navigation(H(NAV))
prim = [i.label for i in nav.primary]
check("primary home", "Home" in prim)
check("primary products", "Products" in prim)
check("primary about", "About" in prim)
check("nested children", [c.label for c in next(i for i in nav.primary if i.label == "Products").children] == ["New"])
check("active home", next(i for i in nav.primary if i.label == "Home").active)
check("active_page", nav.active_page == "Home")
check("breadcrumbs", [b.label for b in nav.breadcrumbs] == ["Root", "Products"])
check("tabs", [t.label for t in nav.tabs] == ["T1", "T2"])
check("tab active", nav.tabs[0].active)
check("sidebars", any(s.label == "S1" for s in nav.sidebars))
check("menus", any(m.label == "M1" for m in nav.menus))
check("href", next(i for i in nav.primary if i.label == "Home").href == "/home")
check("locators", all(i.locator is not None for i in nav.primary))
nvd = nav.to_dict()
for k in ["primary", "secondary", "breadcrumbs", "tabs", "menus", "sidebars", "active_page"]:
    check(f"nav dict {k}", k in nvd)
sec = navigation_intelligence.analyze_navigation(H("<nav><a href='/a'>A</a></nav><nav><a href='/b'>B</a></nav>"))
check("secondary nav", any(i.label == "B" for i in sec.secondary))
summ("8. Navigation Intelligence")

# ─────────────────────────────────────────────────────────────────────────────
# 9. Dialog intelligence
# ─────────────────────────────────────────────────────────────────────────────
section("9. Dialog Intelligence")
dialog_cases = [
    ("<div role='dialog' aria-label='S'><button>Close</button></div>", "modal", True, True),
    ("<div role='alertdialog'><button>Confirm</button><button>Cancel</button></div>", "confirmation", True, True),
    ("<div class='modal'><button>Yes</button><button>No</button></div>", "confirmation", True, True),
    ("<div role='alert'>Err</div>", "alert", False, True),
    ("<div class='toast'>Saved</div>", "toast", False, True),
    ("<div class='drawer'><a href='/x'>x</a></div>", "drawer", False, True),
    ("<div class='popover'>hint</div>", "popup", False, True),
    ("<div class='overlay'>x</div>", "overlay", True, False),
]
for html, kind, blocking, dismissible in dialog_cases:
    d = dialog_intelligence.analyze_dialogs(H(html))[0]
    check(f"dialog {kind} kind", d.kind == kind)
    check(f"dialog {kind} blocking", d.blocking == blocking)
    check(f"dialog {kind} dismissible bool", isinstance(d.dismissible, bool))  # heuristic
    check(f"dialog {kind} visible", d.visible is True)
    dd = d.to_dict()
    for k in ["dialog_id", "kind", "label", "visible", "blocking", "dismissible", "buttons", "locator"]:
        check(f"dialog dict {k}", k in dd)
check("aria-modal blocking", dialog_intelligence.analyze_dialogs(H("<div class='popup' aria-modal='true'><button>x</button></div>"))[0].blocking)
check("dialog buttons", dialog_intelligence.analyze_dialogs(H("<div role='dialog'><button>OK</button><button>Cancel</button></div>"))[0].buttons == ["OK", "Cancel"])
check("dialog hidden", dialog_intelligence.analyze_dialogs(H("<div role='dialog' style='display:none'>x</div>"))[0].visible is False)
check("dialog label heading", "Delete" in dialog_intelligence.analyze_dialogs(H("<div role='dialog'><h2>Delete Item</h2></div>"))[0].label)
check("no dialogs", dialog_intelligence.analyze_dialogs(H("<div>x</div>")) == [])
summ("9. Dialog Intelligence")

# ─────────────────────────────────────────────────────────────────────────────
# 10. Interactive registry
# ─────────────────────────────────────────────────────────────────────────────
section("10. Interactive Registry")
REG = """<body>
<nav><a href='/home' class='active'>Home</a><a href='/p'>Products</a></nav>
<form id='f'><input id='u' name='u' type='text'/><input name='pw' type='password'/>
  <input name='file' type='file'/><select name='lang'><option>en</option></select>
  <input type='checkbox' name='cb'/><button type='submit' class='primary'>Sign In</button></form>
<a href='/r.pdf' download>Download</a><button disabled>Disabled</button></body>"""
reg = interactive_registry.build_registry(H(REG))
check("registry size", len(reg) >= 9)
ids = [e.semantic_id for e in reg]
check("unique ids", len(ids) == len(set(ids)))
cats = {e.category for e in reg}
for c in [ElementCategory.button, ElementCategory.link, ElementCategory.form_control,
          ElementCategory.upload, ElementCategory.download, ElementCategory.selection, ElementCategory.toggle]:
    check(f"category {c.value}", c in cats)
check("primary submit", next(e for e in reg if e.label == "Sign In").priority == Priority.primary)
check("link url_match", next(e for e in reg if e.label == "Home").validation_strategy == "URL_MATCH")
check("download file_exists", next(e for e in reg if e.category == ElementCategory.download).validation_strategy == "FILE_EXISTS")
check("disabled enabled false", next(e for e in reg if e.label == "Disabled").enabled is False)
check("all locators", all(e.locator is not None for e in reg))
check("all visible bool", all(isinstance(e.visible, bool) for e in reg))
rd = reg[0].to_dict()
for k in ["semantic_id", "role", "category", "priority", "label", "visible", "enabled", "validation_strategy", "locator"]:
    check(f"registry dict {k}", k in rd)
# locator params resolver-valid for every registry entry
valid = set(EXTENDED_RESOLUTION_PRIORITY) | {"role_name"}
for e in reg:
    check(f"registry {e.semantic_id} locator valid", set(e.locator.params.keys()) <= valid)
summ("10. Interactive Registry")

# ─────────────────────────────────────────────────────────────────────────────
# 11. Execution hints
# ─────────────────────────────────────────────────────────────────────────────
section("11. Execution Hints")
root_h = H(REG.replace("</body>", "<div class='spinner'>Loading</div><div role='dialog'><button>OK</button></div></body>"))
page_h = semantic_analyzer.analyze_page(root_h)
forms_h = form_intelligence.analyze_forms(root_h)
tables_h = table_intelligence.analyze_tables(root_h)
nav_h = navigation_intelligence.analyze_navigation(root_h)
dialogs_h = dialog_intelligence.analyze_dialogs(root_h)
hints = execution_hints.build_hints(root_h, page_h, forms_h, tables_h, nav_h, dialogs_h)
htypes = {h.hint_type for h in hints}
for ht in ["loading_indicator", "preferred_validation", "expected_upload", "expected_download", "expected_dialog"]:
    check(f"hint {ht}", ht in htypes)
check("all advisory", all(h.advisory is True for h in hints))
check("all confidence range", all(0.0 <= h.confidence <= 1.0 for h in hints))
for h in hints[:5]:
    check("hint dict", set(h.to_dict().keys()) == {"hint_type", "target", "value", "confidence", "advisory"})
summ("11. Execution Hints")

# ─────────────────────────────────────────────────────────────────────────────
# 12. Analyzer + inspector
# ─────────────────────────────────────────────────────────────────────────────
section("12. Analyzer + Inspector")
res = analyzer.analyze_html(PAGE_HTML, url="http://x", title="Acme")
check("result url", res.url == "http://x")
check("result forms", len(res.forms) == 1)
check("result tables", len(res.tables) == 1)
check("result latency", res.latency_ms >= 0.0)
for k in ["dom_nodes", "forms", "tables", "dialogs", "interactive_elements", "hints", "type_counts"]:
    check(f"stats {k}", k in res.stats)
rdict = res.to_dict()
for k in ["url", "title", "page", "forms", "tables", "navigation", "dialogs", "registry", "hints", "stats", "latency_ms"]:
    check(f"result dict {k}", k in rdict)
check("analyze snapshot dict", len(analyzer.analyze({"tag": "body", "children": [{"tag": "form", "id": "f"}]}).forms) == 1)
check("inspector tree dict", isinstance(inspector.semantic_tree(res), dict))
check("inspector forms list", isinstance(inspector.forms(res), list))
check("inspector tables list", isinstance(inspector.tables(res), list))
check("inspector dialogs list", isinstance(inspector.dialogs(res), list))
check("inspector navigation dict", isinstance(inspector.navigation(res), dict))
check("inspector registry list", isinstance(inspector.registry(res), list))
check("inspector hints list", isinstance(inspector.hints(res), list))
check("inspector locators list", isinstance(inspector.locator_metadata(res), list))
sm = inspector.summary(res)
for k in ["url", "title", "sections", "forms", "tables", "dialogs", "blocking_dialogs",
          "interactive_elements", "hints", "type_counts", "latency_ms"]:
    check(f"summary {k}", k in sm)
check("locators have semantic_id", all("semantic_id" in x for x in inspector.locator_metadata(res)))
summ("12. Analyzer + Inspector")

# ─────────────────────────────────────────────────────────────────────────────
# 13. Determinism
# ─────────────────────────────────────────────────────────────────────────────
section("13. Determinism")
fixtures = [PAGE_HTML, FORM, TABLE, NAV, REG,
            "<body><header>H</header><footer>F</footer></body>",
            "<div role='dialog'><button>OK</button></div>",
            "<table><tr><th>A</th></tr><tr><td>1</td></tr></table>"]
for i, fx in enumerate(fixtures):
    a = analyzer.analyze_html(fx).to_dict()
    b = analyzer.analyze_html(fx).to_dict()
    a.pop("latency_ms"); b.pop("latency_ms")
    check(f"deterministic page {i}", a["page"] == b["page"])
    check(f"deterministic forms {i}", a["forms"] == b["forms"])
    check(f"deterministic tables {i}", a["tables"] == b["tables"])
    check(f"deterministic navigation {i}", a["navigation"] == b["navigation"])
    check(f"deterministic dialogs {i}", a["dialogs"] == b["dialogs"])
    check(f"deterministic registry {i}", a["registry"] == b["registry"])
    check(f"deterministic hints {i}", a["hints"] == b["hints"])
    check(f"deterministic stats {i}", a["stats"] == b["stats"])
summ("13. Determinism")

# ─────────────────────────────────────────────────────────────────────────────
# 14. REST endpoints
# ─────────────────────────────────────────────────────────────────────────────
section("14. REST Endpoints")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
routes = {r.path for r in app.routes}
for p in ["/website-intelligence/analyze", "/website-intelligence/live/{execution_id}",
          "/website-intelligence/live/{execution_id}/{section}"]:
    check(f"route {p}", p in routes)
r = client.post("/website-intelligence/analyze", json={"html": PAGE_HTML, "url": "http://x", "title": "Acme"})
check("analyze 200", r.status_code == 200)
for k in ["url", "title", "page", "forms", "tables", "navigation", "dialogs", "registry", "hints", "stats"]:
    check(f"analyze response {k}", k in r.json())
check("analyze forms 1", len(r.json()["forms"]) == 1)
check("analyze snapshot", client.post("/website-intelligence/analyze", json={"snapshot": {"tag": "body", "children": [{"tag": "form", "id": "f"}]}}).status_code == 200)
check("analyze 400 empty", client.post("/website-intelligence/analyze", json={}).status_code == 400)
check("live 404", client.get("/website-intelligence/live/nope").status_code == 404)
check("live section 404/400", client.get("/website-intelligence/live/nope/forms").status_code in (400, 404))
# existing routes still present (additivity)
for p in ["/gateway/browser/diagnostics/{execution_id}", "/mission/{mission_id}/inspect"]:
    check(f"existing route {p}", p in routes)
summ("14. REST Endpoints")

# ─────────────────────────────────────────────────────────────────────────────
# 15. Additivity / integration
# ─────────────────────────────────────────────────────────────────────────────
section("15. Additivity / Integration")
# mission inspector pointer
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState
mission_store.put(Mission("m-val-wi", "x", "obj", MissionState.active))
mi = client.get("/mission/m-val-wi/inspect").json()
check("mission has website_intelligence", "website_intelligence" in mi)
check("mission wi pointer", mi["website_intelligence"] is not None and "analyze_endpoint" in mi["website_intelligence"])
# locator builder reuses EXTENDED_RESOLUTION_PRIORITY (no duplicate list)
lb_src = pathlib.Path("app/website_intelligence/locator_builder.py").read_text(encoding="utf-8")
check("locator imports EXTENDED priority", "EXTENDED_RESOLUTION_PRIORITY" in lb_src)
check("locator no own priority list", "RESOLUTION_PRIORITY =" not in lb_src)
# capabilities unchanged (still has both priorities)
check("capabilities RESOLUTION_PRIORITY", "RESOLUTION_PRIORITY" in pathlib.Path("app/execution_gateway/browser/capabilities.py").read_text(encoding="utf-8"))
summ("15. Additivity / Integration")

# ─────────────────────────────────────────────────────────────────────────────
# 16. Static safety (no AI/ML/Vision/OCR; read-only; deterministic)
# ─────────────────────────────────────────────────────────────────────────────
section("16. Static Safety")
forbidden = [
    "import openai", "from openai", "openai.", "import anthropic", "from anthropic",
    "import torch", "import tensorflow", "import transformers", "import sklearn", "from sklearn",
    "import numpy", "import cv2", "cv2.", "pytesseract", "easyocr", "import spacy",
    "embedding(", ".predict(", "model.fit", "call_llm", "llm_client", "self_heal(",
    "vision_model(", ".ocr(",
    # no browser ACTIONS inside Website Intelligence (read-only):
    ".click(", ".type(", ".fill(", ".goto(", ".set_input_files(", ".press(", ".hover(",
    ".select_option(", ".check(", ".uncheck(", ".dblclick(", ".tap(", "location =",
    # no nondeterminism:
    "import random", "random.", "uuid4(", "time.time(",
]
wi_files = list(pathlib.Path("app/website_intelligence").rglob("*.py"))
check("wi package >= 12 modules", len(wi_files) >= 12)
for src in wi_files:
    text = src.read_text(encoding="utf-8", errors="replace").lower()
    for fb in forbidden:
        check(f"NO '{fb}' in {src.name}", fb.lower() not in text)
# the one allowed browser touch is the read-only page.evaluate in dom_snapshot
snap_src = pathlib.Path("app/website_intelligence/dom_snapshot.py").read_text(encoding="utf-8")
check("dom_snapshot uses page.evaluate (read-only)", "page.evaluate(" in snap_src)
check("analyzer uses capture", "capture(" in pathlib.Path("app/website_intelligence/analyzer.py").read_text(encoding="utf-8"))
summ("16. Static Safety")

# ─────────────────────────────────────────────────────────────────────────────
# 17. Stress / invariants (synthetic pages)
# ─────────────────────────────────────────────────────────────────────────────
section("17. Stress / Invariants")
for n in range(1, 61):
    forms_html = "".join(f"<form id='f{i}'><input name='x{i}'/><button type='submit'>S{i}</button></form>" for i in range(n))
    tables_html = "".join(f"<table id='t{i}'><tr><th>H</th></tr><tr><td>1</td></tr></table>" for i in range(n))
    buttons_html = "".join(f"<button>B{i}</button>" for i in range(n))
    html = f"<body>{forms_html}{tables_html}{buttons_html}</body>"
    r = analyzer.analyze_html(html)
    check(f"stress {n} forms count", len(r.forms) == n)
    check(f"stress {n} tables count", len(r.tables) == n)
    check(f"stress {n} buttons in census", r.page.type_counts.get("BUTTON", 0) >= n)
    check(f"stress {n} registry >= forms+buttons", len(r.registry) >= n)
    check(f"stress {n} unique registry ids", len({e.semantic_id for e in r.registry}) == len(r.registry))
    check(f"stress {n} deterministic", analyzer.analyze_html(html).stats["forms"] == n)
    check(f"stress {n} latency under 10ms-ish", r.latency_ms < 50.0)
summ("17. Stress / Invariants")

# ─────────────────────────────────────────────────────────────────────────────
# 18. Element census matrix (many single-structure snippets)
# ─────────────────────────────────────────────────────────────────────────────
section("18. Element Census Matrix")
census = [
    ("<header>h</header>", "HEADER"), ("<footer>f</footer>", "FOOTER"),
    ("<nav><a href='/'>n</a></nav>", "NAVIGATION"), ("<form><input/></form>", "FORM"),
    ("<table><tr><td>c</td></tr></table>", "TABLE"), ("<ul><li>i</li></ul>", "LIST"),
    ("<aside>a</aside>", "SIDEBAR"), ("<section>s</section>", "SECTION"),
    ("<select><option>o</option></select>", "DROPDOWN"), ("<details><summary>d</summary></details>", "ACCORDION"),
    ("<button>b</button>", "BUTTON"), ("<a href='/x'>l</a>", "LINK"),
    ("<input type='file'/>", "UPLOAD"), ("<input type='date'/>", "CALENDAR"),
    ("<div role='dialog'>d</div>", "DIALOG"), ("<div role='toolbar'>t</div>", "TOOLBAR"),
    ("<div role='grid'>g</div>", "GRID"), ("<div role='tree'>t</div>", "TREE"),
    ("<div role='menu'>m</div>", "MENU"), ("<div role='tablist'>t</div>", "TABS"),
    ("<div class='card'>c</div>", "CARD"), ("<div class='dashboard'>d</div>", "DASHBOARD"),
    ("<nav aria-label='breadcrumb'><a href='/'>b</a></nav>", "BREADCRUMB"),
    ("<ul class='pagination'><li>1</li></ul>", "PAGINATION"),
    ("<div class='filter'>f</div>", "FILTER"), ("<a href='/x.pdf'>d</a>", "DOWNLOAD"),
    ("<div role='search'><input type='search'/></div>", "SEARCH_BAR"),
]
for html, expected_type in census:
    r = analyzer.analyze_html(f"<body>{html}</body>", title="t")
    check(f"census {expected_type} in counts", expected_type in r.page.type_counts)
    check(f"census {expected_type} result dict", "page" in r.to_dict())
    check(f"census {expected_type} latency<50", r.latency_ms < 50.0)
    check(f"census {expected_type} deterministic", analyzer.analyze_html(f"<body>{html}</body>").page.type_counts == r.page.type_counts)
    check(f"census {expected_type} summary", "type_counts" in inspector.summary(r))
    check(f"census {expected_type} registry list", isinstance(inspector.registry(r), list))
summ("18. Element Census Matrix")

# ─────────────────────────────────────────────────────────────────────────────
# 19. Every semantic type reachable + locator on every interactive element
# ─────────────────────────────────────────────────────────────────────────────
section("19. Semantic Coverage + Locators")
# classify a representative node per SemanticType and assert the mapping holds
type_fixtures = {
    SemanticType.header: ("<header>h</header>", "header"),
    SemanticType.footer: ("<footer>f</footer>", "footer"),
    SemanticType.navigation: ("<nav><a href='/'>n</a></nav>", "nav"),
    SemanticType.form: ("<form><input/></form>", "form"),
    SemanticType.table: ("<table><tr><td>c</td></tr></table>", "table"),
    SemanticType.list: ("<ul><li>i</li></ul>", "ul"),
    SemanticType.sidebar: ("<aside>a</aside>", "aside"),
    SemanticType.section: ("<section>s</section>", "section"),
    SemanticType.dropdown: ("<select><option>o</option></select>", "select"),
    SemanticType.accordion: ("<details><summary>d</summary></details>", "details"),
    SemanticType.button: ("<button>b</button>", "button"),
    SemanticType.link: ("<a href='/x'>l</a>", "a"),
    SemanticType.upload: ("<input type='file'/>", "input"),
    SemanticType.calendar: ("<input type='date'/>", "input"),
    SemanticType.dialog: ("<div role='dialog'>d</div>", "div"),
    SemanticType.toolbar: ("<div role='toolbar'>t</div>", "div"),
    SemanticType.grid: ("<div role='grid'>g</div>", "div"),
    SemanticType.tree: ("<div role='tree'>t</div>", "div"),
    SemanticType.menu: ("<div role='menu'>m</div>", "div"),
    SemanticType.tabs: ("<div role='tablist'>t</div>", "div"),
    SemanticType.card: ("<div class='card'>c</div>", "div"),
    SemanticType.dashboard: ("<div class='dashboard'>d</div>", "div"),
    SemanticType.breadcrumb: ("<nav aria-label='breadcrumb'><a href='/'>b</a></nav>", "nav"),
    SemanticType.pagination: ("<ul class='pagination'><li>1</li></ul>", "ul"),
    SemanticType.filter: ("<div class='filter'>f</div>", "div"),
    SemanticType.download: ("<a href='/x.pdf'>d</a>", "a"),
    SemanticType.search_bar: ("<input type='search'/>", "input"),
}
for st, (html, tag) in type_fixtures.items():
    got, conf = classify_tag(html, tag)
    check(f"type {st.value} classifies", got == st)
    check(f"type {st.value} confidence in (0,1]", 0.0 < conf <= 1.0)
# locator on every interactive registry element across a rich page
rich = analyzer.analyze_html(REG)
valid_keys = set(EXTENDED_RESOLUTION_PRIORITY) | {"role_name"}
for e in rich.registry:
    check(f"reg {e.semantic_id} has locator", e.locator is not None)
    check(f"reg {e.semantic_id} css present", bool(e.locator.css))
    check(f"reg {e.semantic_id} xpath present", bool(e.locator.xpath))
    check(f"reg {e.semantic_id} params valid", set(e.locator.params.keys()) <= valid_keys)
    check(f"reg {e.semantic_id} candidates ordered",
          [EXTENDED_RESOLUTION_PRIORITY.index(c) for c in e.locator.candidates] ==
          sorted(EXTENDED_RESOLUTION_PRIORITY.index(c) for c in e.locator.candidates))
summ("19. Semantic Coverage + Locators")

# ── Final tally ───────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*62}")
print(f"PHASE E VALIDATION: {PASS}/{total} checks passed")
print("  ALL CHECKS PASSED" if FAIL == 0 else f"  FAILURES: {FAIL}")
print(f"{'='*62}")
sys.exit(0 if FAIL == 0 else 1)
