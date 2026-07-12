from benchmark.m0_task_runner import TaskRunner
from benchmark.fakes import page


def _runner():
    return TaskRunner(
        driver=None,
        client=None,
        executor_mode="playwright",
        run_id="t",
        artifacts_dir=".",
    )


def _sig(ctx: dict) -> str:
    return _runner()._semantic_signature(ctx)


def test_filling_password_field_changes_semantic_signature_without_raw_value():
    empty = page("http://x/login", text="Login", elements=[
        {"selector": "#password", "type": "input", "state": {"filled": False}},
    ])
    filled = page("http://x/login", text="Login", elements=[
        {"selector": "#password", "type": "input", "state": {"filled": True}},
    ])

    assert _sig(empty) != _sig(filled)
    texts = TaskRunner._semantic_texts(filled)
    assert "#password:filled=True" in texts
    assert "secret123" not in texts


def test_checking_checkbox_changes_semantic_signature():
    unchecked = page("http://x/register", text="Register", elements=[
        {"selector": "#tos", "type": "input", "state": {"checked": False}},
    ])
    checked = page("http://x/register", text="Register", elements=[
        {"selector": "#tos", "type": "input", "state": {"checked": True}},
    ])

    assert _sig(unchecked) != _sig(checked)
    assert "#tos:checked=True" in TaskRunner._semantic_texts(checked)


def test_visible_text_changes_semantic_signature_as_before():
    before = page("http://x/a", text="Page one")
    after = page("http://x/a", text="Page two")

    assert _sig(before) != _sig(after)


def test_identical_form_state_produces_identical_semantic_signature():
    first = page("http://x/register", text="Register", elements=[
        {"selector": "#email", "type": "input", "state": {"value": "a@example.com"}},
        {"selector": "#password", "type": "input", "state": {"filled": True}},
        {"selector": "#tos", "type": "input", "state": {"checked": True}},
    ])
    second = page("http://x/register", text="Register", elements=[
        {"selector": "#email", "type": "input", "state": {"value": "a@example.com"}},
        {"selector": "#password", "type": "input", "state": {"filled": True}},
        {"selector": "#tos", "type": "input", "state": {"checked": True}},
    ])

    assert _sig(first) == _sig(second)
