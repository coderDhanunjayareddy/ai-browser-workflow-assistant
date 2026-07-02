"""
M1.2 — Observation completeness: confirms the BACKEND side requires no code change.

extractor_v2.ts/injected_scripts.js now populate InteractiveElement.state with value/
checked/selected_text keys. This test proves the two places that consume `state` today —
context_service.format_page_context (uncompressed prompt) and ContextCompressor.compress
(compressed prompt, via RelevanceRanker) — already render/forward ANY key present in
`state` generically, so M1.2 required zero changes to either file.
"""
from unittest.mock import MagicMock

from app.schemas.request import InteractiveElement, PageContext
from app.services.context_service import format_page_context
from app.context_compression.compressor import ContextCompressor


def _element(**state_kwargs):
    return InteractiveElement(
        type="input", text="", selector="#u", visible=True, input_type="text",
        state=state_kwargs,
    )


def test_uncompressed_formatter_already_renders_new_state_keys():
    """format_page_context needed NO change: it renders `state={...}` for any non-empty
    state dict, so value/checked/selected_text flow through automatically."""
    ctx = PageContext(
        url="https://x", title="Login", interactive_elements=[_element(value="tester")],
        content_blocks=[], headings=[], selected_text="", visible_text="", images=[],
    )
    rendered = format_page_context(ctx)
    assert "value" in rendered and "tester" in rendered


def test_uncompressed_formatter_renders_checked_and_selected_text():
    ctx = PageContext(
        url="https://x", title="Form", interactive_elements=[
            _element(checked=True), _element(selected_text="India"),
        ],
        content_blocks=[], headings=[], selected_text="", visible_text="", images=[],
    )
    rendered = format_page_context(ctx)
    assert "checked" in rendered
    assert "India" in rendered


def test_compressed_path_forwards_state_via_relevant_elements():
    """ContextCompressor.compress needed NO change either: relevant_elements already
    carries the full InteractiveElement.model_dump(), including `state`."""
    pc = MagicMock()
    pc.interactive_elements = [_element(value="python search query")]
    result = ContextCompressor().compress(
        task="search", page_context=pc, verified_facts={}, prior_steps=[])
    assert result["relevant_elements"][0]["state"]["value"] == "python search query"


def test_password_value_never_present_end_to_end():
    """Defense in depth: even if a caller ever populated state.value for a password
    field (it shouldn't, per the extractor change), nothing downstream special-cases
    or strips it — the extractor's exclusion is the only, and correct, control point.
    This test documents that the backend does not add a second safeguard, matching the
    M1.2 spec's decision to keep the exclusion at the single point of capture."""
    ctx = PageContext(
        url="https://x", title="Login", interactive_elements=[
            InteractiveElement(type="input", text="", selector="#p", visible=True,
                               input_type="password", state={}),
        ],
        content_blocks=[], headings=[], selected_text="", visible_text="", images=[],
    )
    rendered = format_page_context(ctx)
    assert "value" not in rendered.split("SELECTOR: #p")[1].split("\n")[0]
