"""
Phase F — Workflow Certification Scenarios (declarative).

Each scenario binds a fixture + a workflow (built as planner ExecutionSteps) + success
criteria. Steps use ONLY the existing planner ActionType set (navigate/input/click/
wait/extract/validate) so they run through the unchanged gateway + Playwright adapter.

Upload/download file mechanics have no planner ActionType (documented Phase D limitation),
so those scenarios certify page load + semantic structure here, and the actual file
transfer is certified at the adapter level in the real-browser suite.
"""
from __future__ import annotations

from app.certification.models import (
    CertificationScenario, ScenarioCategory, SuccessCriterion, CriterionKind,
)
from app.execution_planning.models import (
    ActionType, TargetType, ValidationStrategy, make_step,
)


def _nav(order, base_url, path):
    return make_step(order, ActionType.navigate, TargetType.url, base_url + path,
                     parameters={"url": base_url + path})

def _crit(kind, detail="", step_index=None, target=None, value=None):
    return SuccessCriterion(kind=kind, detail=detail, step_index=step_index, target=target, value=value)


# Each builder returns a list of ExecutionSteps for the given base_url.

def _login(b):
    return [
        _nav(1, b, "/login"),
        make_step(2, ActionType.input, TargetType.form, "username",
                  parameters={"testid": "username", "value": "tester",
                              "validate_after": {"value_equals": "tester"}}),
        make_step(3, ActionType.input, TargetType.form, "password",
                  parameters={"testid": "password", "value": "secret123"}),
        make_step(4, ActionType.click, TargetType.element, "sign in",
                  parameters={"testid": "login-btn", "validate_after": {"text_contains": "Welcome"}}),
        make_step(5, ActionType.validate, TargetType.page, "welcome text",
                  parameters={"expected_text": "Welcome"}, expected_result="Welcome",
                  validation_strategy=ValidationStrategy.text_match),
    ]

def _register(b):
    return [
        _nav(1, b, "/register"),
        make_step(2, ActionType.input, TargetType.form, "email",
                  parameters={"testid": "email", "value": "new@x.com"}),
        make_step(3, ActionType.input, TargetType.form, "password",
                  parameters={"testid": "pw", "value": "longenough"}),
        make_step(4, ActionType.click, TargetType.element, "accept terms",
                  parameters={"testid": "tos"}),
        make_step(5, ActionType.click, TargetType.element, "register",
                  parameters={"testid": "reg-btn", "validate_after": {"text_contains": "Account created"}}),
    ]

def _search(b):
    return [
        _nav(1, b, "/search"),
        make_step(2, ActionType.input, TargetType.form, "query",
                  parameters={"id": "q", "value": "Book"}),
        make_step(3, ActionType.click, TargetType.element, "search",
                  parameters={"testid": "go", "validate_after": {"text_contains": "results"}}),
        make_step(4, ActionType.extract, TargetType.region, "result count",
                  parameters={"id": "count", "mode": "text"}),
    ]

def _filter(b):
    return [
        _nav(1, b, "/search"),
        make_step(2, ActionType.input, TargetType.form, "query",
                  parameters={"id": "q", "value": "Toy"}),
        make_step(3, ActionType.click, TargetType.element, "search",
                  parameters={"testid": "go", "validate_after": {"text_contains": "results"}}),
        make_step(4, ActionType.extract, TargetType.region, "result count",
                  parameters={"id": "count", "mode": "text"}),
    ]

def _edit_row(b):
    return [
        _nav(1, b, "/crud"),
        make_step(2, ActionType.click, TargetType.element, "edit row",
                  parameters={"testid": "edit-1", "validate_after": {"text_contains": "Row updated"}}),
        make_step(3, ActionType.validate, TargetType.page, "row updated",
                  parameters={"expected_text": "Row updated"}, expected_result="Row updated",
                  validation_strategy=ValidationStrategy.text_match),
    ]

def _upload(b):
    return [
        _nav(1, b, "/upload"),
        make_step(2, ActionType.validate, TargetType.element, "file input present",
                  parameters={"css": "#file"}, validation_strategy=ValidationStrategy.dom_presence),
    ]

def _download(b):
    return [
        _nav(1, b, "/download"),
        make_step(2, ActionType.validate, TargetType.element, "download link present",
                  parameters={"id": "dl"}, validation_strategy=ValidationStrategy.dom_presence),
    ]

def _navigate_pages(b):
    return [
        _nav(1, b, "/dashboard"),
        make_step(2, ActionType.click, TargetType.element, "go to records",
                  parameters={"text": "Records"}),
        make_step(3, ActionType.extract, TargetType.region, "records heading",
                  parameters={"css": "h1", "mode": "text"}),
    ]

def _dashboard_refresh(b):
    return [
        _nav(1, b, "/dashboard"),
        make_step(2, ActionType.click, TargetType.element, "refresh",
                  parameters={"testid": "refresh", "validate_after": {"text_contains": "Dashboard refreshed"}}),
    ]

def _nested_nav(b):
    return [
        _nav(1, b, "/nav"),
        make_step(2, ActionType.click, TargetType.element, "guides",
                  parameters={"testid": "nav-guides", "validate_after": {"text_contains": "Guides content"}}),
        make_step(3, ActionType.click, TargetType.element, "install",
                  parameters={"testid": "nav-install", "validate_after": {"text_contains": "Install content"}}),
    ]

def _confirm(b):
    return [
        _nav(1, b, "/confirm"),
        make_step(2, ActionType.click, TargetType.element, "delete",
                  parameters={"testid": "delete"}),
        make_step(3, ActionType.click, TargetType.element, "confirm yes",
                  parameters={"testid": "yes", "validate_after": {"text_contains": "Item deleted"}}),
    ]

def _modal(b):
    return [
        _nav(1, b, "/modal"),
        make_step(2, ActionType.click, TargetType.element, "open modal", parameters={"testid": "open"}),
        make_step(3, ActionType.input, TargetType.form, "setting",
                  parameters={"testid": "setting", "value": "off"}),
        make_step(4, ActionType.click, TargetType.element, "save",
                  parameters={"testid": "save", "validate_after": {"text_contains": "Setting saved"}}),
    ]

def _recover_delayed(b):
    return [
        _nav(1, b, "/dynamic"),
        make_step(2, ActionType.click, TargetType.element, "late ready button",
                  parameters={"testid": "ready", "timeout_ms": 300}),
    ]

def _resume_transient(b):
    return [
        _nav(1, b, "/dynamic"),
        make_step(2, ActionType.click, TargetType.element, "late ready button",
                  parameters={"testid": "ready", "timeout_ms": 300,
                              "validate_after": {"text_contains": "Loaded"}}),
    ]

def _dynamic_loading(b):
    return [
        _nav(1, b, "/dynamic"),
        make_step(2, ActionType.wait, TargetType.element, "wait for ready",
                  parameters={"testid": "ready", "state": "visible", "timeout_ms": 2000}),
        make_step(3, ActionType.click, TargetType.element, "ready", parameters={"testid": "ready"}),
    ]

def _pagination(b):
    return [
        _nav(1, b, "/pagination"),
        make_step(2, ActionType.click, TargetType.element, "next page",
                  parameters={"testid": "next", "validate_after": {"text_contains": "page 2"}}),
    ]

def _multistep(b):
    return [
        _nav(1, b, "/multistep"),
        make_step(2, ActionType.input, TargetType.form, "full name",
                  parameters={"testid": "fullname", "value": "Ada"}),
        make_step(3, ActionType.click, TargetType.element, "next", parameters={"testid": "next1"}),
        make_step(4, ActionType.input, TargetType.form, "role",
                  parameters={"testid": "role", "value": "Engineer"}),
        make_step(5, ActionType.click, TargetType.element, "finish",
                  parameters={"testid": "finish", "validate_after": {"text_contains": "Onboarding complete"}}),
    ]

def _tabs(b):
    return [
        _nav(1, b, "/tabs"),
        make_step(2, ActionType.click, TargetType.element, "billing tab",
                  parameters={"testid": "tab-billing", "validate_after": {"text_contains": "Billing panel"}}),
    ]

def _accordion(b):
    return [
        _nav(1, b, "/accordion"),
        make_step(2, ActionType.click, TargetType.element, "expand q2",
                  parameters={"testid": "q2", "validate_after": {"text_contains": "q2 expanded"}}),
    ]

def _toast(b):
    return [
        _nav(1, b, "/toast"),
        make_step(2, ActionType.click, TargetType.element, "save",
                  parameters={"testid": "trigger", "validate_after": {"text_contains": "Saved successfully"}}),
    ]

def _infinite_scroll(b):
    return [
        _nav(1, b, "/scroll"),
        make_step(2, ActionType.click, TargetType.element, "load more",
                  parameters={"testid": "more", "validate_after": {"text_contains": "6 posts"}}),
    ]

def _missing_bounded(b):
    return [
        _nav(1, b, "/login"),
        make_step(2, ActionType.click, TargetType.element, "ghost element",
                  parameters={"selector": "#never-exists", "timeout_ms": 300}),
    ]

def _ambiguous_guard(b):
    # /crud has two "Edit" buttons -> a strict text locator is ambiguous and must fail FAST
    # (classified AmbiguousLocator, attempts==1) rather than burn recovery cycles.
    return [
        _nav(1, b, "/crud"),
        make_step(2, ActionType.click, TargetType.element, "ambiguous edit (two matches)",
                  parameters={"text": "Edit", "strict": True, "timeout_ms": 300}),
    ]

def _dragdrop(b):
    return [
        _nav(1, b, "/dragdrop"),
        make_step(2, ActionType.validate, TargetType.element, "draggable present",
                  parameters={"testid": "drag"}, validation_strategy=ValidationStrategy.dom_presence),
    ]


def build_scenarios() -> list[CertificationScenario]:
    S, C, K = ScenarioCategory, SuccessCriterion, CriterionKind
    return [
        CertificationScenario(
            "cert-login", "Login: fill & submit", "login-app",
            "Fill username/password and submit, expecting a welcome", S.form_submit, "/login",
            "Form submits; 'Welcome tester' is shown",
            [_crit(K.state_completed, "execution completes"),
             _crit(K.min_completed_steps, "all 5 steps complete", value=5),
             _crit(K.post_validation, "click validates welcome text", step_index=3),
             _crit(K.semantic_present, "form detected", target="form")],
            build_steps=_login),
        CertificationScenario(
            "cert-register", "Registration: form with checkbox", "register-app",
            "Fill email/password, accept terms, submit", S.form_submit, "/register",
            "Account created shown",
            [_crit(K.state_completed), _crit(K.post_validation, "register confirms", step_index=4),
             _crit(K.semantic_present, "form detected", target="form")],
            build_steps=_register),
        CertificationScenario(
            "cert-search", "Search data", "catalog-app",
            "Type a query and search", S.search, "/search",
            "Result count shown",
            [_crit(K.state_completed), _crit(K.post_validation, "search shows results", step_index=2),
             _crit(K.content_contains, "count extracted", step_index=3, target="results"),
             _crit(K.semantic_present, "search bar detected", target="search_bar")],
            build_steps=_search),
        CertificationScenario(
            "cert-filter", "Filter results", "catalog-app",
            "Filter the catalog by a term", S.filter, "/search",
            "Filtered count shown",
            [_crit(K.state_completed), _crit(K.post_validation, "filter shows results", step_index=2),
             _crit(K.content_contains, "count extracted", step_index=3, target="results")],
            build_steps=_filter),
        CertificationScenario(
            "cert-edit-row", "Edit a table row", "crud-app",
            "Click Edit on a row and confirm update", S.table_edit, "/crud",
            "Row updated shown",
            [_crit(K.state_completed), _crit(K.post_validation, "edit confirms", step_index=1),
             _crit(K.semantic_present, "table detected", target="table")],
            build_steps=_edit_row),
        CertificationScenario(
            "cert-upload", "Upload a file", "upload-app",
            "Load upload page; certify file input", S.upload, "/upload",
            "Upload control present",
            [_crit(K.state_completed), _crit(K.semantic_present, "upload detected", target="upload")],
            known_limitations=["File transfer certified at adapter level (PlaywrightAdapter.upload); "
                               "planner ActionType set has no UPLOAD."],
            build_steps=_upload),
        CertificationScenario(
            "cert-download", "Download a report", "download-app",
            "Load download page; certify download affordance", S.download, "/download",
            "Download link present",
            [_crit(K.state_completed), _crit(K.semantic_present, "download detected", target="download")],
            known_limitations=["File transfer certified at adapter level (PlaywrightAdapter.download); "
                               "planner ActionType set has no DOWNLOAD."],
            build_steps=_download),
        CertificationScenario(
            "cert-navigate", "Navigate multiple pages", "docs-app",
            "From dashboard, click Records and land on the records page", S.navigation, "/dashboard",
            "Records page heading shown",
            [_crit(K.state_completed), _crit(K.content_contains, "records heading", step_index=2, target="Records")],
            build_steps=_navigate_pages),
        CertificationScenario(
            "cert-dashboard", "Dashboard refresh", "dashboard-app",
            "Refresh the dashboard", S.navigation, "/dashboard",
            "Dashboard refreshed shown",
            [_crit(K.state_completed), _crit(K.post_validation, "refresh confirms", step_index=1),
             _crit(K.semantic_present, "dashboard detected", target="dashboard")],
            build_steps=_dashboard_refresh),
        CertificationScenario(
            "cert-nested-nav", "Nested navigation", "docs-app",
            "Open a nested nav item", S.navigation, "/nav",
            "Install content shown",
            [_crit(K.state_completed), _crit(K.post_validation, "nested nav confirms", step_index=2),
             _crit(K.semantic_present, "navigation detected", target="navigation")],
            build_steps=_nested_nav),
        CertificationScenario(
            "cert-confirm", "Confirmation dialog", "confirm-app",
            "Trigger and confirm a delete dialog", S.dialog, "/confirm",
            "Item deleted shown",
            [_crit(K.state_completed), _crit(K.post_validation, "confirm deletes", step_index=2),
             _crit(K.semantic_present, "dialog detected", target="dialog")],
            build_steps=_confirm),
        CertificationScenario(
            "cert-modal", "Modal dialog edit", "modal-app",
            "Open a modal, edit, and save", S.dialog, "/modal",
            "Setting saved shown",
            [_crit(K.state_completed), _crit(K.post_validation, "modal save confirms", step_index=3),
             _crit(K.semantic_present, "dialog detected", target="dialog")],
            build_steps=_modal),
        CertificationScenario(
            "cert-recover", "Recover from delayed element", "dynamic-app",
            "Click an element that appears late; deterministic recovery retries", S.recovery, "/dynamic",
            "Recovers and completes",
            [_crit(K.state_completed), _crit(K.recovery_used, "recovery engaged", step_index=1),
             _crit(K.min_completed_steps, "both steps complete", value=2)],
            build_steps=_recover_delayed),
        CertificationScenario(
            "cert-resume", "Resume after transient failure", "dynamic-app",
            "Transient miss recovers and the workflow continues", S.resume, "/dynamic",
            "Loaded shown after recovery",
            [_crit(K.state_completed), _crit(K.recovery_used, "recovery engaged", step_index=1),
             _crit(K.post_validation, "post-recovery validation", step_index=1)],
            build_steps=_resume_transient),
        CertificationScenario(
            "cert-dynamic", "Dynamic loading with explicit wait", "dynamic-app",
            "Wait for a late element then act", S.dynamic_loading, "/dynamic",
            "Waits and completes",
            [_crit(K.state_completed), _crit(K.min_completed_steps, "all 3 steps complete", value=3)],
            build_steps=_dynamic_loading),
        CertificationScenario(
            "cert-pagination", "Pagination", "pagination-app",
            "Go to the next page", S.pagination, "/pagination",
            "page 2 shown",
            [_crit(K.state_completed), _crit(K.post_validation, "next page confirms", step_index=1),
             _crit(K.semantic_present, "pagination detected", target="pagination")],
            build_steps=_pagination),
        CertificationScenario(
            "cert-multistep", "Multi-step form", "wizard-app",
            "Complete a two-step wizard", S.multistep, "/multistep",
            "Onboarding complete shown",
            [_crit(K.state_completed), _crit(K.post_validation, "wizard finishes", step_index=4),
             _crit(K.min_completed_steps, "all 5 steps complete", value=5)],
            build_steps=_multistep),
        CertificationScenario(
            "cert-tabs", "Tabs", "account-app",
            "Switch to the billing tab", S.tabs, "/tabs",
            "Billing panel shown",
            [_crit(K.state_completed), _crit(K.post_validation, "tab switch confirms", step_index=1),
             _crit(K.semantic_present, "tabs detected", target="tabs")],
            build_steps=_tabs),
        CertificationScenario(
            "cert-accordion", "Accordion", "faq-app",
            "Expand an accordion item", S.accordion, "/accordion",
            "q2 expanded shown",
            [_crit(K.state_completed), _crit(K.post_validation, "expand confirms", step_index=1),
             _crit(K.semantic_present, "accordion detected", target="accordion")],
            build_steps=_accordion),
        CertificationScenario(
            "cert-toast", "Toast notification", "toast-app",
            "Trigger a toast", S.toast, "/toast",
            "Saved successfully toast shown",
            [_crit(K.state_completed), _crit(K.post_validation, "toast appears", step_index=1)],
            build_steps=_toast),
        CertificationScenario(
            "cert-infinite-scroll", "Infinite scroll (load more)", "feed-app",
            "Load more feed items", S.infinite_scroll, "/scroll",
            "6 posts shown",
            [_crit(K.state_completed), _crit(K.post_validation, "more loads", step_index=1)],
            build_steps=_infinite_scroll),
        CertificationScenario(
            "cert-bounded-failure", "Bounded failure on missing element", "login-app",
            "Click a non-existent element; fail within bounded attempts (no infinite loop)",
            S.recovery, "/login", "Fails bounded; attempts <= 3",
            [_crit(K.bounded_failure, "bounded failure", step_index=1, value=3)],
            expect_failure=True, build_steps=_missing_bounded),
        CertificationScenario(
            "cert-ambiguous-guard", "Ambiguous locator fails fast (reliability guard)", "crud-app",
            "A strict locator matching >1 element fails fast as AmbiguousLocator (no wasted recovery)",
            S.recovery, "/crud", "Bounded fail-fast; category=AmbiguousLocator; attempts<=1",
            [_crit(K.bounded_failure, "fails within 1 attempt (permanent, no retry)", step_index=1, value=1),
             _crit(K.failure_category, "classified AmbiguousLocator", step_index=1, target="AmbiguousLocator")],
            expect_failure=True, build_steps=_ambiguous_guard,
            known_limitations=["Production workflows should set strict:true on destructive actions; the "
                               "platform fails fast on ambiguity rather than acting on the wrong element."]),
        CertificationScenario(
            "cert-dragdrop", "Drag-and-drop (analysis only)", "board-app",
            "Certify draggable presence (no synthetic drag gesture)", S.drag_drop, "/dragdrop",
            "Draggable present",
            [_crit(K.state_completed), _crit(K.semantic_present, "card detected", target="card")],
            known_limitations=["Analysis-only: no synthetic drag gesture is performed (no browser autonomy)."],
            build_steps=_dragdrop),
    ]
