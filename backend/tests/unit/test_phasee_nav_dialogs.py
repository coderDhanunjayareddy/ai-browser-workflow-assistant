"""Phase E — Unit tests: navigation_intelligence.py + dialog_intelligence.py."""
import pytest
from app.website_intelligence import dom_snapshot, navigation_intelligence, dialog_intelligence


NAV = """
<body>
  <nav aria-label="Primary"><ul>
    <li><a href="/home" class="active">Home</a></li>
    <li><a href="/products">Products</a>
        <ul><li><a href="/products/new">New</a></li><li><a href="/products/sale">Sale</a></li></ul></li>
    <li><a href="/about">About</a></li>
  </ul></nav>
  <nav aria-label="breadcrumb"><ol>
    <li><a href="/">Root</a></li><li><a href="/products">Products</a></li>
  </ol></nav>
  <div role="tablist"><button role="tab" aria-selected="true">Tab1</button><button role="tab">Tab2</button></div>
  <aside class="sidebar"><a href="/s1">Side1</a><a href="/s2">Side2</a></aside>
  <div role="menu"><a href="/m1">M1</a></div>
</body>
"""


def _nav(html):
    return navigation_intelligence.analyze_navigation(dom_snapshot.from_html(html))


class TestNavigation:
    def test_primary(self):
        n = _nav(NAV)
        labels = [i.label for i in n.primary]
        assert "Home" in labels and "Products" in labels and "About" in labels

    def test_hierarchy(self):
        n = _nav(NAV)
        products = next(i for i in n.primary if i.label == "Products")
        child_labels = [c.label for c in products.children]
        assert "New" in child_labels and "Sale" in child_labels

    def test_active(self):
        n = _nav(NAV)
        home = next(i for i in n.primary if i.label == "Home")
        assert home.active is True
        assert n.active_page == "Home"

    def test_breadcrumbs(self):
        n = _nav(NAV)
        assert [b.label for b in n.breadcrumbs] == ["Root", "Products"]

    def test_tabs(self):
        n = _nav(NAV)
        assert [t.label for t in n.tabs] == ["Tab1", "Tab2"]
        assert n.tabs[0].active is True

    def test_sidebars(self):
        n = _nav(NAV)
        assert any(s.label == "Side1" for s in n.sidebars)

    def test_menus(self):
        n = _nav(NAV)
        assert any(m.label == "M1" for m in n.menus)

    def test_hrefs(self):
        n = _nav(NAV)
        assert next(i for i in n.primary if i.label == "Home").href == "/home"

    def test_locators(self):
        n = _nav(NAV)
        assert all(i.locator is not None for i in n.primary)

    def test_to_dict(self):
        d = _nav(NAV).to_dict()
        for k in ["primary", "secondary", "breadcrumbs", "tabs", "menus", "sidebars", "active_page"]:
            assert k in d

    def test_secondary(self):
        html = "<nav><a href='/a'>A</a></nav><nav><a href='/b'>B</a></nav>"
        n = _nav(html)
        assert any(i.label == "A" for i in n.primary)
        assert any(i.label == "B" for i in n.secondary)


def _dialogs(html):
    return dialog_intelligence.analyze_dialogs(dom_snapshot.from_html(html))


class TestDialogs:
    def test_modal(self):
        d = _dialogs("<div role='dialog' aria-label='Settings'><button>Close</button></div>")[0]
        assert d.kind == "modal"
        assert d.blocking is True
        assert d.dismissible is True

    def test_confirmation(self):
        d = _dialogs("<div role='alertdialog'><button>Confirm</button><button>Cancel</button></div>")[0]
        assert d.kind == "confirmation"
        assert "Confirm" in d.buttons and "Cancel" in d.buttons

    def test_confirmation_from_buttons(self):
        d = _dialogs("<div class='modal'><button>Yes</button><button>No</button></div>")[0]
        assert d.kind == "confirmation"

    def test_alert(self):
        d = _dialogs("<div role='alert'>Error!</div>")[0]
        assert d.kind == "alert"

    def test_toast(self):
        d = _dialogs("<div class='toast'>Saved</div>")[0]
        assert d.kind == "toast"
        assert d.blocking is False
        assert d.dismissible is True

    def test_drawer(self):
        d = _dialogs("<div class='drawer'><a href='/x'>x</a></div>")[0]
        assert d.kind == "drawer"

    def test_popup(self):
        d = _dialogs("<div class='popover'>hint</div>")[0]
        assert d.kind == "popup"

    def test_overlay_blocking(self):
        d = _dialogs("<div class='overlay'>x</div>")[0]
        assert d.kind == "overlay"
        assert d.blocking is True

    def test_aria_modal(self):
        d = _dialogs("<div class='popup' aria-modal='true'><button>x</button></div>")[0]
        assert d.blocking is True

    def test_buttons(self):
        d = _dialogs("<div role='dialog'><button>OK</button><button>Cancel</button></div>")[0]
        assert d.buttons == ["OK", "Cancel"]

    def test_visible(self):
        d = _dialogs("<div role='dialog' style='display:none'>x</div>")[0]
        assert d.visible is False

    def test_label(self):
        d = _dialogs("<div role='dialog'><h2>Delete Item</h2></div>")[0]
        assert "Delete Item" in d.label

    def test_to_dict(self):
        d = _dialogs("<div role='dialog'><button>x</button></div>")[0].to_dict()
        for k in ["dialog_id", "kind", "label", "visible", "blocking", "dismissible", "buttons", "locator"]:
            assert k in d

    def test_no_dialogs(self):
        assert _dialogs("<div>nothing</div>") == []
