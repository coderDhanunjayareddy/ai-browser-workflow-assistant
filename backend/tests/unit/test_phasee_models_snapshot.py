"""Phase E — Unit tests: models.py (DomNode) + dom_snapshot.py."""
import pytest
from app.website_intelligence import dom_snapshot
from app.website_intelligence.models import DomNode


class TestDomNode:
    def test_basic(self):
        n = DomNode(tag="div", classes="a b c", text="hi")
        assert n.tag == "div"
        assert n.class_list == ["a", "b", "c"]
        assert n.has_class("b")
        assert not n.has_class("z")
        assert n.class_contains("a", "z")

    def test_walk_and_descendants(self):
        root = DomNode(tag="div", children=[DomNode(tag="p"), DomNode(tag="span", children=[DomNode(tag="a")])])
        assert root.node_count() == 4
        assert len(list(root.descendants())) == 3

    def test_find(self):
        root = dom_snapshot.from_html("<div><button id='b'>X</button><a href='/y'>Y</a></div>")
        assert root.find_first(lambda n: n.tag == "button").id == "b"
        assert len(root.find_by_tag("a")) == 1
        assert len(root.find_all(lambda n: n.tag in ("button", "a"))) == 2

    def test_text_content(self):
        root = dom_snapshot.from_html("<div>Hello <b>World</b></div>")
        d = root.find_first(lambda n: n.tag == "div")
        assert "Hello" in d.text_content()
        assert "World" in d.text_content()

    def test_to_dict(self):
        n = DomNode(tag="input", name="q", type="text")
        d = n.to_dict()
        for k in ["tag", "role", "id", "classes", "name", "type", "visible", "disabled", "attrs"]:
            assert k in d


class TestFromHtml:
    def test_parses_tree(self):
        root = dom_snapshot.from_html("<body><header><h1>T</h1></header><main><p>x</p></main></body>")
        assert root.tag == "body"
        assert root.find_first(lambda n: n.tag == "header") is not None
        assert root.find_first(lambda n: n.tag == "main") is not None

    def test_attributes_extracted(self):
        root = dom_snapshot.from_html(
            '<div><input id="e" name="email" type="email" placeholder="P" aria-label="A" data-testid="t" required/></div>')
        inp = root.find_first(lambda n: n.tag == "input")
        assert inp.id == "e"
        assert inp.name == "email"
        assert inp.type == "email"
        assert inp.placeholder == "P"
        assert inp.aria_label == "A"
        assert inp.testid == "t"
        assert "required" in inp.attrs

    def test_void_elements(self):
        root = dom_snapshot.from_html("<div><br/><img src='x'/><input type='text'/></div>")
        assert len(root.find_by_tag("br")) == 1
        assert len(root.find_by_tag("img")) == 1
        assert len(root.find_by_tag("input")) == 1

    def test_visibility_inline_style(self):
        root = dom_snapshot.from_html(
            "<div><span style='display:none'>hidden</span><span>shown</span></div>")
        spans = root.find_by_tag("span")
        assert spans[0].visible is False
        assert spans[1].visible is True

    def test_hidden_attr(self):
        root = dom_snapshot.from_html("<div hidden>x</div>")
        assert root.find_first(lambda n: n.tag == "div").visible is False

    def test_disabled(self):
        root = dom_snapshot.from_html("<button disabled>x</button>")
        assert root.find_first(lambda n: n.tag == "button").disabled is True

    def test_role_extracted(self):
        root = dom_snapshot.from_html("<div role='dialog'>x</div>")
        assert root.find_first(lambda n: n.tag == "div").role == "dialog"

    def test_href(self):
        root = dom_snapshot.from_html("<a href='/path'>L</a>")
        assert root.find_first(lambda n: n.tag == "a").href == "/path"

    def test_empty_html(self):
        root = dom_snapshot.from_html("")
        assert isinstance(root, DomNode)


class TestFromDict:
    def test_roundtrip(self):
        d = {"tag": "form", "id": "f1", "attrs": {"role": "form"}, "role": "form",
             "children": [{"tag": "input", "name": "q", "type": "text"}]}
        node = dom_snapshot.from_dict(d)
        assert node.tag == "form"
        assert node.id == "f1"
        assert node.role == "form"
        assert len(node.children) == 1
        assert node.children[0].name == "q"

    def test_empty_dict(self):
        node = dom_snapshot.from_dict({})
        assert node.tag == "body"

    def test_capture_js_constant(self):
        # the capture script exists and is a read-only evaluate (no click/type/goto)
        js = dom_snapshot.CAPTURE_JS
        assert "document.body" in js
        for forbidden in [".click(", ".type(", ".goto(", ".fill(", "window.location ="]:
            assert forbidden not in js
