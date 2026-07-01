"""Phase E — Unit tests: semantic_analyzer.py + locator_builder.py."""
import pytest
from app.website_intelligence import dom_snapshot, semantic_analyzer, locator_builder
from app.website_intelligence.models import SemanticType
from app.execution_gateway.browser.capabilities import EXTENDED_RESOLUTION_PRIORITY


def _node(html):
    return dom_snapshot.from_html(html)


def _classify(html, tag):
    root = _node(html)
    target = root.find_first(lambda n: n.tag == tag) or root
    return semantic_analyzer.classify(target)


class TestClassification:
    @pytest.mark.parametrize("html,tag,expected", [
        ("<header><h1>x</h1></header>", "header", SemanticType.header),
        ("<footer>x</footer>", "footer", SemanticType.footer),
        ("<nav><a href='/'>H</a></nav>", "nav", SemanticType.navigation),
        ("<form><input name='q'/></form>", "form", SemanticType.form),
        ("<table><tr><td>x</td></tr></table>", "table", SemanticType.table),
        ("<ul><li>a</li></ul>", "ul", SemanticType.list),
        ("<aside>x</aside>", "aside", SemanticType.sidebar),
        ("<section>x</section>", "section", SemanticType.section),
        ("<select><option>a</option></select>", "select", SemanticType.dropdown),
        ("<details><summary>s</summary>x</details>", "details", SemanticType.accordion),
        ("<button>x</button>", "button", SemanticType.button),
        ("<a href='/y'>y</a>", "a", SemanticType.link),
    ])
    def test_by_tag(self, html, tag, expected):
        stype, conf = _classify(html, tag)
        assert stype == expected
        assert conf > 0

    @pytest.mark.parametrize("html,tag,expected", [
        ("<div role='dialog'>x</div>", "div", SemanticType.dialog),
        ("<div role='banner'>x</div>", "div", SemanticType.header),
        ("<div role='navigation'><a href='/'>h</a></div>", "div", SemanticType.navigation),
        ("<div role='toolbar'>x</div>", "div", SemanticType.toolbar),
        ("<div role='grid'>x</div>", "div", SemanticType.grid),
        ("<div role='tree'>x</div>", "div", SemanticType.tree),
        ("<div role='menu'>x</div>", "div", SemanticType.menu),
        ("<div role='tablist'>x</div>", "div", SemanticType.tabs),
        ("<div role='search'>x</div>", "div", SemanticType.search_bar),
    ])
    def test_by_role(self, html, tag, expected):
        stype, conf = _classify(html, tag)
        assert stype == expected

    @pytest.mark.parametrize("html,tag,expected", [
        ("<div class='card'>x</div>", "div", SemanticType.card),
        ("<div class='dashboard'>x</div>", "div", SemanticType.dashboard),
        ("<div class='sidebar'>x</div>", "div", SemanticType.sidebar),
        ("<div class='toolbar'>x</div>", "div", SemanticType.toolbar),
        ("<div class='accordion'>x</div>", "div", SemanticType.accordion),
        ("<ul class='pagination'><li>1</li></ul>", "ul", SemanticType.pagination),
        ("<nav aria-label='breadcrumb'><a href='/'>r</a></nav>", "nav", SemanticType.breadcrumb),
        ("<div class='filter'>x</div>", "div", SemanticType.filter),
    ])
    def test_by_class(self, html, tag, expected):
        stype, conf = _classify(html, tag)
        assert stype == expected

    def test_upload(self):
        assert _classify("<input type='file'/>", "input")[0] == SemanticType.upload

    def test_download(self):
        assert _classify("<a href='/x.pdf'>D</a>", "a")[0] == SemanticType.download
        assert _classify("<a href='/x' download>D</a>", "a")[0] == SemanticType.download

    def test_calendar(self):
        assert _classify("<input type='date'/>", "input")[0] == SemanticType.calendar

    def test_unknown(self):
        assert semantic_analyzer.classify(dom_snapshot.from_html("<span>x</span>").find_first(lambda n: n.tag == "span"))[0] is None


class TestPageModel:
    def test_page_tree(self):
        html = """<body><header><h1>Site</h1></header><nav><a href='/'>H</a></nav>
        <main><form id='f'><input name='q'/></form><table><tr><th>A</th></tr></table></main>
        <footer>F</footer></body>"""
        page = semantic_analyzer.analyze_page(dom_snapshot.from_html(html), url="http://x", title="Site")
        section_types = [c.type for c in page.root.walk()]
        assert SemanticType.header in section_types
        assert SemanticType.navigation in section_types
        assert SemanticType.form in section_types
        assert SemanticType.table in section_types
        assert SemanticType.footer in section_types

    def test_root_is_page(self):
        page = semantic_analyzer.analyze_page(dom_snapshot.from_html("<div>x</div>"), title="T")
        assert page.root.type == SemanticType.page
        assert page.title == "T"

    def test_type_counts(self):
        html = "<div><button>a</button><button>b</button><a href='/x'>l</a></div>"
        page = semantic_analyzer.analyze_page(dom_snapshot.from_html(html))
        assert page.type_counts.get("BUTTON") == 2
        assert page.type_counts.get("LINK") == 1

    def test_sections_listed(self):
        html = "<body><header>H</header><footer>F</footer></body>"
        page = semantic_analyzer.analyze_page(dom_snapshot.from_html(html))
        assert len(page.sections) >= 2

    def test_node_to_dict(self):
        page = semantic_analyzer.analyze_page(dom_snapshot.from_html("<form><input/></form>"))
        d = page.root.to_dict()
        for k in ["type", "label", "interactive", "confidence", "locator", "children"]:
            assert k in d


class TestLocatorBuilder:
    def test_priority_order(self):
        node = dom_snapshot.from_html('<button id="b" data-testid="t" name="n">Go</button>').find_first(lambda n: n.tag == "button")
        loc = locator_builder.build_locator(node, text="Go")
        # testid beats id/name/text in EXTENDED priority
        assert loc.primary_strategy == "testid"
        assert "testid" in loc.params
        # candidates respect resolver priority order
        idx = [EXTENDED_RESOLUTION_PRIORITY.index(c) for c in loc.candidates]
        assert idx == sorted(idx)

    def test_css_fallback_always(self):
        node = dom_snapshot.from_html("<div>x</div>").find_first(lambda n: n.tag == "div")
        loc = locator_builder.build_locator(node)
        assert loc.css
        assert loc.xpath

    def test_id_css(self):
        node = dom_snapshot.from_html('<div id="main">x</div>').find_first(lambda n: n.tag == "div")
        loc = locator_builder.build_locator(node)
        assert loc.css == "div#main"
        assert loc.xpath == '//*[@id="main"]'

    def test_text_for_button(self):
        node = dom_snapshot.from_html("<button>Save</button>").find_first(lambda n: n.tag == "button")
        loc = locator_builder.build_locator(node, text="Save")
        assert loc.params.get("text") == "Save"

    def test_role_name(self):
        node = dom_snapshot.from_html("<div role='button' aria-label='Submit'>x</div>").find_first(lambda n: n.tag == "div")
        loc = locator_builder.build_locator(node)
        assert loc.params.get("role") == "button"
        assert loc.params.get("role_name") == "Submit"

    def test_params_resolver_compatible(self):
        # every emitted strategy key (except helper role_name) is a valid resolver strategy
        node = dom_snapshot.from_html('<input id="e" name="q" placeholder="P" aria-label="A" data-testid="t"/>').find_first(lambda n: n.tag == "input")
        loc = locator_builder.build_locator(node)
        valid = set(EXTENDED_RESOLUTION_PRIORITY) | {"role_name"}
        assert set(loc.params.keys()) <= valid

    def test_locator_to_dict(self):
        node = dom_snapshot.from_html('<input id="e"/>').find_first(lambda n: n.tag == "input")
        d = locator_builder.build_locator(node).to_dict()
        for k in ["primary_strategy", "params", "candidates", "css", "xpath"]:
            assert k in d
