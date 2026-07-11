from benchmark.m0_models import CriterionResult, M0Criterion, M0CriterionKind as K
from benchmark.strategy_generation import build_strategy_context


def test_repeated_identical_semantic_failures_produce_strategy_context():
    ctx = build_strategy_context(
        goal="Find the product price",
        success_criteria=[M0Criterion(K.extracted_value_present, target="price")],
        validation_results=[
            CriterionResult(K.extracted_value_present.value, "price evidence", False,
                            "key~='price' in analysis=False")
        ],
        page_context={"url": "https://shop.test/search", "title": "Search", "visible_text": "results"},
        outcome_kind="report",
        strategy_key="report",
        convergence_reason="goal convergence stalled",
    )

    assert "Expected semantic goal: Find the product price" in ctx.text
    assert "Observed evidence:" in ctx.text
    assert "Contradiction detected:" in ctx.text
    assert "Repeatedly failed strategy: repeated unsupported report" in ctx.text
    assert "Avoid next: unsupported reports" in ctx.text


def test_different_contradictions_produce_different_strategy_contexts():
    page_one = build_strategy_context(
        goal="Go to page 2",
        success_criteria=[M0Criterion(K.dom_text_present, target="Page 2")],
        validation_results=[
            CriterionResult(K.dom_text_present.value, "page marker", False,
                            "text~='Page 2' found=False")
        ],
        page_context={"url": "http://x/pagination#1", "title": "Page 1", "visible_text": "Page 1"},
        outcome_kind="click",
        strategy_key="click|#p2|",
        convergence_reason="goal convergence stalled",
    )
    search_results = build_strategy_context(
        goal="Open product detail page",
        success_criteria=[M0Criterion(K.url_matches, target=r"/dp/")],
        validation_results=[
            CriterionResult(K.url_matches.value, "product detail URL", False,
                            "url='https://amazon.test/s?k=headphones'")
        ],
        page_context={
            "url": "https://amazon.test/s?k=headphones",
            "title": "Search results",
            "visible_text": "headphones results",
        },
        outcome_kind="click",
        strategy_key="click|a.product|",
        convergence_reason="goal convergence stalled",
    )

    assert page_one.context_key != search_results.context_key
    assert "Page 2" in page_one.text
    assert "/dp/" in search_results.text
    assert page_one.text != search_results.text
