"""
Grounding Sprint — RelevanceRanker unit tests.

M-G2: the selector string is now part of the term-overlap text pool, so an unlabeled
element whose selector carries task-relevant tokens (e.g. "#nav-search-submit-button")
can out-rank a labeled decoy that merely mentions the task's domain in its aria-label.

M-G3a: ties (equal score) are now broken by geometric position (topmost, then leftmost)
before falling back to DOM order, using the already-captured bounding_box — no new data
source, no schema change.

Amazon Search Action Selection: a genuine actionable control (role=="button" / native
submit) receives an action-relevance bonus so it is preferred over a same-scoring
navigational link decoy (the Amazon #nav-assist-search keyboard-shortcut hint).
"""
from app.context_compression.relevance_ranker import RelevanceRanker


def _el(**kwargs):
    base = {
        "type": "button",
        "text": "",
        "selector": "",
        "visible": True,
        "aria_label": None,
        "accessibility_name": None,
        "placeholder": None,
        "role": None,
        "bounding_box": {},
    }
    base.update(kwargs)
    return base


# ── M-G2: selector-string signal ─────────────────────────────────────────────

def test_unlabeled_button_with_relevant_selector_beats_unlabeled_irrelevant_selector():
    # Isolates the mechanism: with text/aria held equal (both empty), a selector
    # that carries task-relevant tokens must outscore one that carries none.
    relevant = _el(type="input", text="", selector="#nav-search-submit-button")
    irrelevant = _el(type="input", text="", selector="#nav-cart-icon-widget")
    ranked = RelevanceRanker().rank("search for a product", [irrelevant, relevant])
    assert ranked[0]["selector"] == "#nav-search-submit-button"


def test_amazon_search_action_selection_prefers_real_submit_over_shortcut_decoy():
    # Amazon Search Action Selection — acceptance test, faithful reconstruction of
    # amazon_in__product_search_price from the real captured DOM snapshot
    # (m0-nightly-1783015760/.../step_005.json), using the real task goal text.
    #
    # Score evolution against this exact formula (each stage evidence-verified):
    #   pre-M-G2:            real_submit=4,  decoy=16   (original root cause)
    #   post-M-G2:           real_submit=14, decoy=16   (selector tokens added; gap narrows, no flip)
    #   post-M-R1 (role fix) real_submit=14, decoy=16   (submit role textbox->button; still no flip)
    #   post-M-R7 (this fix) real_submit=17, decoy=16   (actionable-affordance +3 flips it)
    #
    # The submit control is captured as role="button" after M-R1 (was "textbox") and
    # carries input_type="submit"; the decoy is a role="link" keyboard-shortcut hint.
    real_submit = _el(
        type="input", input_type="submit", role="button",
        text="", selector="#nav-search-submit-button",
        aria_label=None, accessibility_name="",
    )
    decoy = _el(
        type="a", role="link",
        text="Search alt /", selector="#nav-assist-search",
        aria_label="Search, alt, forward slash",
        accessibility_name="Search, alt, forward slash",
    )
    task = ('Search for "wireless headphones" on Amazon India, open the first '
            'result, and extract the price')
    ranked = RelevanceRanker().rank(task, [decoy, real_submit])
    assert ranked[0]["selector"] == "#nav-search-submit-button"


def test_action_relevance_does_not_apply_without_actionable_affordance():
    # Guard: the affordance bonus keys off role=="button" / native submit only.
    # A role="link" element must NOT receive it, so the signal cannot silently
    # promote every link over every non-actionable element.
    link = _el(type="a", role="link", text="", selector="#a-link")
    plain = _el(type="input", role="textbox", text="", selector="#a-textbox")
    button = _el(type="input", role="button", input_type="submit", text="", selector="#a-button")
    ranked = RelevanceRanker().rank("go", [link, plain, button])
    assert ranked[0]["selector"] == "#a-button"


def test_selector_alone_does_not_outweigh_a_true_text_match():
    # A plain text/aria match should still win over a same-scoring selector-only hit
    # when the text match is stronger overall.
    text_match = _el(text="Search flights", selector="#s1")
    selector_only = _el(text="", selector="#search-button-generic")
    ranked = RelevanceRanker().rank("search flights", [selector_only, text_match])
    assert ranked[0]["selector"] == "#s1"


def test_selector_terms_are_tokenized_on_non_alnum_boundaries():
    # "#nav-search-submit-button" must split into distinct terms, not one opaque token.
    el = _el(selector="#nav-search-submit-button")
    ranked = RelevanceRanker().rank("submit", [el])
    assert ranked[0]["selector"] == "#nav-search-submit-button"
    # sanity: an element whose selector has no overlapping terms scores lower
    other = _el(selector="#totally-unrelated-widget")
    ranked2 = RelevanceRanker().rank("submit", [other, el])
    assert ranked2[0]["selector"] == "#nav-search-submit-button"


# ── M-G3a: position-based tie-break ──────────────────────────────────────────

def test_equal_score_ties_prefer_topmost_element():
    low = _el(text="item", selector="#a", bounding_box={"x": 0, "y": 400})
    high = _el(text="item", selector="#b", bounding_box={"x": 0, "y": 50})
    ranked = RelevanceRanker().rank("item", [low, high])
    assert ranked[0]["selector"] == "#b"


def test_equal_score_and_equal_y_ties_prefer_leftmost_element():
    right = _el(text="item", selector="#a", bounding_box={"x": 300, "y": 100})
    left = _el(text="item", selector="#b", bounding_box={"x": 10, "y": 100})
    ranked = RelevanceRanker().rank("item", [right, left])
    assert ranked[0]["selector"] == "#b"


def test_exact_position_tie_falls_back_to_dom_order():
    first = _el(text="item", selector="#first", bounding_box={"x": 0, "y": 0})
    second = _el(text="item", selector="#second", bounding_box={"x": 0, "y": 0})
    ranked = RelevanceRanker().rank("item", [first, second])
    assert ranked[0]["selector"] == "#first"


def test_missing_bounding_box_defaults_to_origin_and_does_not_crash():
    no_bbox = _el(text="item", selector="#no-bbox")
    no_bbox.pop("bounding_box")
    with_bbox = _el(text="item", selector="#with-bbox", bounding_box={"x": 5, "y": 5})
    ranked = RelevanceRanker().rank("item", [with_bbox, no_bbox])
    # missing bbox treated as (0, 0) -> topmost/leftmost -> ranks first on position
    assert ranked[0]["selector"] == "#no-bbox"


def test_duplicate_announce_elements_are_disambiguated_by_position_not_raw_index():
    # Reconstruction of amazon_in__add_to_cart: N structurally-identical candidates
    # (#a-autoid-N-announce) tie at an exact score; position must break the tie
    # deterministically instead of collapsing to whichever happened to appear last
    # in DOM order at a lower index.
    duplicates = [
        _el(text="", selector=f"#a-autoid-{i}-announce", role="button",
            bounding_box={"x": 20, "y": 200 + i * 40})
        for i in range(5)
    ]
    # shuffle DOM order so index alone would pick the wrong one
    shuffled = [duplicates[3], duplicates[1], duplicates[4], duplicates[0], duplicates[2]]
    ranked = RelevanceRanker().rank("add to cart", shuffled)
    assert ranked[0]["selector"] == "#a-autoid-0-announce"
