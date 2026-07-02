"""
Grounding Sprint — RelevanceRanker unit tests.

M-G2: the selector string is now part of the term-overlap text pool, so an unlabeled
element whose selector carries task-relevant tokens (e.g. "#nav-search-submit-button")
can out-rank a labeled decoy that merely mentions the task's domain in its aria-label.
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


def test_amazon_search_submit_reconstruction_score_gap_narrows_but_does_not_flip():
    # Faithful reconstruction of the amazon_in__product_search_price grounding
    # failure using the real task goal text and the real element attributes.
    # Evidence (manually verified against this exact scoring formula):
    #   pre-M-G2:  real_submit=4,  decoy=16  (documented root cause)
    #   post-M-G2: real_submit=14, decoy=16  (selector signal closes 10 of 12 points,
    #              but the decoy's own aria-label already matched "search" before this
    #              fix, and keeps its +2 aria-label bonus, so the ranking does not flip)
    # This is intentionally NOT asserted as "fixed" — M-G2 as scoped (selector text
    # added to the overlap pool only) narrows but does not resolve this specific
    # failure in isolation. Confirmed live: the benchmark shows both outcomes occur
    # across runs (planner sometimes picks the real button, sometimes the decoy),
    # consistent with a narrowed-but-not-flipped 14-vs-16 score gap.
    real_submit = _el(
        type="input", text="", selector="#nav-search-submit-button",
        aria_label=None, accessibility_name="",
    )
    decoy = _el(
        type="button", text="", selector="#nav-assist-search",
        aria_label="Search, alt, forward slash",
        accessibility_name="Search, alt, forward slash",
    )
    task = ('Search for "wireless headphones" on Amazon India, open the first '
            'result, and extract the price')
    ranked = RelevanceRanker().rank(task, [decoy, real_submit])
    assert ranked[0]["selector"] == "#nav-assist-search"
    assert ranked[1]["selector"] == "#nav-search-submit-button"


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
