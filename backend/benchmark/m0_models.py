"""
M0 — Benchmark domain models (pure data; no behavior, no browser, no AI).

Self-contained dataclasses for declaring real-site benchmark tasks and recording their
outcomes. Criteria here are evaluated against M0's OWN page/loop state (URL, DOM text,
extracted analysis, step counts) — NOT against the gateway ExecutionRecord that the Phase F
certification criteria use. M0 therefore carries its own criterion + failure enums.

Reused from app.certification.models elsewhere: WorkflowOutcome (reliability feed),
OutcomeStatus is mirrored here as TaskStatus with the extra real-site states (blocked/stuck).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class Difficulty(str, Enum):
    simple  = "simple"
    medium  = "medium"
    complex = "complex"


class ExecutorMode(str, Enum):
    playwright = "playwright"   # Mode A: trusted CDP input (upper bound)
    synthetic  = "synthetic"    # Mode B: extension executor_v2 synthetic events (production reality)


class TaskStatus(str, Enum):
    completed = "COMPLETED"
    failed    = "FAILED"
    timeout   = "TIMEOUT"
    blocked   = "BLOCKED"     # site defense (captcha/auth/rate-limit) — excluded from completion denominator
    stuck     = "STUCK"       # loop made no progress (identical observation + action)
    error     = "ERROR"       # runner/infrastructure error
    skipped   = "SKIPPED"     # not attempted (e.g. missing credentials)


class BenchmarkCategory(str, Enum):
    form_submit     = "FORM_SUBMIT"
    search          = "SEARCH"
    filter          = "FILTER"
    table_edit      = "TABLE_EDIT"
    upload          = "UPLOAD"
    download        = "DOWNLOAD"
    navigation      = "NAVIGATION"
    dialog          = "DIALOG"
    pagination      = "PAGINATION"
    multistep       = "MULTISTEP"
    infinite_scroll = "INFINITE_SCROLL"
    accordion       = "ACCORDION"
    dynamic_loading = "DYNAMIC_LOADING"
    cross_site      = "CROSS_SITE"


class M0CriterionKind(str, Enum):
    url_matches             = "URL_MATCHES"               # final URL matches regex (target)
    dom_element_present     = "DOM_ELEMENT_PRESENT"       # CSS selector resolves >=1 element
    dom_text_present        = "DOM_TEXT_PRESENT"          # text appears in page visible_text/DOM
    dom_text_absent         = "DOM_TEXT_ABSENT"           # text does NOT appear
    extracted_value_present = "EXTRACTED_VALUE_PRESENT"   # AI analysis text contains target token/regex
    extracted_value_matches = "EXTRACTED_VALUE_MATCHES"   # AI analysis text matches regex (detail)
    step_count_in_range     = "STEP_COUNT_IN_RANGE"       # steps_taken <= value
    min_completed_steps     = "MIN_COMPLETED_STEPS"       # steps_taken >= value


class FailureCriterionKind(str, Enum):
    dom_error_present  = "DOM_ERROR_PRESENT"   # an error string appeared on the page
    url_matches_error  = "URL_MATCHES_ERROR"   # URL matched an error pattern (regex)
    http_error         = "HTTP_ERROR"          # an HTTP error code was observed (target = "429" etc.)
    rate_limited       = "RATE_LIMITED"        # explicit rate-limit signal


class FailureCategory(str, Enum):
    grounding            = "GROUNDING"
    planning             = "PLANNING"
    execution            = "EXECUTION"
    validation           = "VALIDATION"
    recovery             = "RECOVERY"
    timeout              = "TIMEOUT"
    blocked_captcha      = "BLOCKED_CAPTCHA"
    blocked_rate_limit   = "BLOCKED_RATE_LIMIT"
    blocked_auth_expired = "BLOCKED_AUTH_EXPIRED"
    blocked_login_wall   = "BLOCKED_LOGIN_WALL"
    blocked_anti_bot     = "BLOCKED_ANTI_BOT"
    perception           = "PERCEPTION"
    orchestration        = "ORCHESTRATION"
    vision_required      = "VISION_REQUIRED"
    infrastructure       = "INFRASTRUCTURE"
    unknown              = "UNKNOWN"


# categories that mean "the site blocked us", NOT "the agent failed" — excluded from
# the completion-rate denominator.
BLOCKED_CATEGORIES = {
    FailureCategory.blocked_captcha,
    FailureCategory.blocked_rate_limit,
    FailureCategory.blocked_auth_expired,
    FailureCategory.blocked_login_wall,
    FailureCategory.blocked_anti_bot,
}


class LocatorStrategy(str, Enum):
    """Ranked locator strategies, highest-confidence first (mirrors locator_engine.LocatorRanker)."""
    accessibility_name = "accessibility_name"
    aria_label         = "aria_label"
    data_testid        = "data_testid"
    text_match         = "text_match"
    css_selector       = "css_selector"
    xpath              = "xpath"


# ── Criterion declarations ──────────────────────────────────────────────────--

@dataclass
class M0Criterion:
    kind:   M0CriterionKind
    detail: str = ""
    target: Optional[str] = None     # regex / selector / text / key
    value:  Optional[int] = None     # numeric bound

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "detail": self.detail, "target": self.target, "value": self.value}


@dataclass
class M0FailureCriterion:
    kind:   FailureCriterionKind
    detail: str = ""
    target: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "detail": self.detail, "target": self.target}


@dataclass
class CriterionResult:
    kind:     str
    detail:   str
    passed:   bool
    observed: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail, "passed": self.passed, "observed": self.observed}


# ── Task definition sub-schemas ─────────────────────────────────────────────--

@dataclass
class Preconditions:
    auth_required:       bool = False
    auth_strategy:       str = "none"            # "none" | "session_state" | "credential_login"
    auth_state_file:     Optional[str] = None    # path relative to benchmark/.playwright_state/
    credentials_key:     Optional[str] = None    # key into .benchmark_secrets
    page_ready_selector: Optional[str] = None    # must be visible before the loop starts
    pre_navigation:      Optional[str] = None    # URL to visit first (cookie consent etc.)

    def to_dict(self) -> dict[str, Any]:
        return {
            "auth_required": self.auth_required, "auth_strategy": self.auth_strategy,
            "auth_state_file": self.auth_state_file, "credentials_key": self.credentials_key,
            "page_ready_selector": self.page_ready_selector, "pre_navigation": self.pre_navigation,
        }


@dataclass
class HumanInterventionRules:
    danger_actions:          str = "require_human"   # "block" | "require_human" | "auto_approve"
    caution_actions:         str = "auto_approve"     # "require_human" | "auto_approve"
    max_human_interventions: int = 0                  # exceed -> task marked BLOCKED (needs human)

    def to_dict(self) -> dict[str, Any]:
        return {
            "danger_actions": self.danger_actions, "caution_actions": self.caution_actions,
            "max_human_interventions": self.max_human_interventions,
        }


@dataclass
class ArtifactSpec:
    artifact_id: str
    type:        str          # "screenshot" | "dom_snapshot" | "extracted_text" | "download_file"
    description: str = ""
    required:    bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"artifact_id": self.artifact_id, "type": self.type,
                "description": self.description, "required": self.required}


@dataclass
class M0TaskDefinition:
    task_id:     str
    site_id:     str
    website:     str
    difficulty:  Difficulty
    category:    BenchmarkCategory
    goal:        str
    start_url:   str                                  # may contain {fixture_base} placeholder
    preconditions:            Preconditions = field(default_factory=Preconditions)
    success_criteria:         list[M0Criterion] = field(default_factory=list)
    failure_criteria:         list[M0FailureCriterion] = field(default_factory=list)
    expected_artifacts:       list[ArtifactSpec] = field(default_factory=list)
    timeout_ms:               int = 120_000
    max_steps:                int = 25
    retry_budget:             int = 2
    human_intervention_rules: HumanInterventionRules = field(default_factory=HumanInterventionRules)
    executor_override:        Optional[str] = None    # "playwright" | "synthetic"
    skip_reason:              Optional[str] = None
    expected_step_range:      Optional[tuple[int, int]] = None
    expect_failure:           bool = False             # known-unsupported workflow (documents a gap)
    is_fixture:               bool = False             # served by the local FixtureServer
    notes:                    str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "site_id": self.site_id, "website": self.website,
            "difficulty": self.difficulty.value, "category": self.category.value,
            "goal": self.goal, "start_url": self.start_url,
            "preconditions": self.preconditions.to_dict(),
            "success_criteria": [c.to_dict() for c in self.success_criteria],
            "failure_criteria": [c.to_dict() for c in self.failure_criteria],
            "expected_artifacts": [a.to_dict() for a in self.expected_artifacts],
            "timeout_ms": self.timeout_ms, "max_steps": self.max_steps,
            "retry_budget": self.retry_budget,
            "human_intervention_rules": self.human_intervention_rules.to_dict(),
            "executor_override": self.executor_override, "skip_reason": self.skip_reason,
            "expected_step_range": list(self.expected_step_range) if self.expected_step_range else None,
            "expect_failure": self.expect_failure, "is_fixture": self.is_fixture, "notes": self.notes,
        }


# ── Step + task result records ──────────────────────────────────────────────--

@dataclass
class M0StepRecord:
    """One loop iteration: observe -> analyze -> gate -> execute -> validate."""
    index:              int
    action_type:        Optional[str] = None
    action_selector:    Optional[str] = None
    action_value:       Optional[str] = None
    safety_level:       Optional[str] = None
    human_intervention: bool = False
    executed:           bool = False
    execution_success:  bool = False
    locator_strategy:   Optional[str] = None     # which LocatorStrategy resolved (Mode A)
    locator_attempts:   int = 0
    validation_passed:  Optional[bool] = None
    validation_detail:  str = ""
    is_recovery:        bool = False
    recovery_success:   Optional[bool] = None
    failure_category:   Optional[str] = None
    error_detail:       str = ""
    # timings (ms)
    observe_ms:  float = 0.0
    analyze_ms:  float = 0.0
    execute_ms:  float = 0.0
    validate_ms: float = 0.0
    # ai accounting
    ai_called:    bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    url_after:   str = ""
    screenshot:  Optional[str] = None     # relative path

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index, "action_type": self.action_type,
            "action_selector": self.action_selector, "action_value": self.action_value,
            "safety_level": self.safety_level, "human_intervention": self.human_intervention,
            "executed": self.executed, "execution_success": self.execution_success,
            "locator_strategy": self.locator_strategy, "locator_attempts": self.locator_attempts,
            "validation_passed": self.validation_passed, "validation_detail": self.validation_detail,
            "is_recovery": self.is_recovery, "recovery_success": self.recovery_success,
            "failure_category": self.failure_category, "error_detail": self.error_detail,
            "observe_ms": round(self.observe_ms, 2), "analyze_ms": round(self.analyze_ms, 2),
            "execute_ms": round(self.execute_ms, 2), "validate_ms": round(self.validate_ms, 2),
            "ai_called": self.ai_called, "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens, "url_after": self.url_after,
            "screenshot": self.screenshot,
        }


@dataclass
class M0TaskResult:
    task_id:     str
    website:     str
    difficulty:  str
    category:    str
    executor_mode: str
    status:      TaskStatus = TaskStatus.error
    expect_failure: bool = False
    steps:       list[M0StepRecord] = field(default_factory=list)
    criteria_results: list[CriterionResult] = field(default_factory=list)
    failure_category: Optional[str] = None
    failure_detail:   str = ""
    final_url:        str = ""
    duration_ms:      float = 0.0
    started_at:       float = 0.0
    # artifacts
    screenshots: list[str] = field(default_factory=list)
    dom_snapshots: list[str] = field(default_factory=list)
    timeline_path: Optional[str] = None

    # ── derived metrics ─────────────────────────────────────────────────────
    @property
    def steps_taken(self) -> int:
        return len(self.steps)

    @property
    def steps_successful(self) -> int:
        return sum(1 for s in self.steps if s.executed and s.execution_success
                   and (s.validation_passed is not False))

    @property
    def steps_failed(self) -> int:
        return sum(1 for s in self.steps if s.executed and not s.execution_success)

    @property
    def human_interventions(self) -> int:
        return sum(1 for s in self.steps if s.human_intervention)

    @property
    def recoveries_attempted(self) -> int:
        return sum(1 for s in self.steps if s.is_recovery)

    @property
    def recoveries_successful(self) -> int:
        return sum(1 for s in self.steps if s.is_recovery and s.recovery_success)

    @property
    def validations_passed(self) -> int:
        return sum(1 for s in self.steps if s.validation_passed is True)

    @property
    def validations_failed(self) -> int:
        return sum(1 for s in self.steps if s.validation_passed is False)

    @property
    def validations_attempted(self) -> int:
        return sum(1 for s in self.steps if s.validation_passed is not None)

    @property
    def ai_calls(self) -> int:
        return sum(1 for s in self.steps if s.ai_called)

    @property
    def total_tokens(self) -> int:
        return sum(s.prompt_tokens + s.completion_tokens for s in self.steps)

    @property
    def observe_time_ms(self) -> float:
        return sum(s.observe_ms for s in self.steps)

    @property
    def analyze_time_ms(self) -> float:
        return sum(s.analyze_ms for s in self.steps)

    @property
    def execute_time_ms(self) -> float:
        return sum(s.execute_ms for s in self.steps)

    @property
    def validate_time_ms(self) -> float:
        return sum(s.validate_ms for s in self.steps)

    @property
    def locator_strategy_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.steps:
            if s.locator_strategy:
                out[s.locator_strategy] = out.get(s.locator_strategy, 0) + 1
        return out

    @property
    def is_completed(self) -> bool:
        return self.status == TaskStatus.completed

    @property
    def is_blocked(self) -> bool:
        return self.status == TaskStatus.blocked

    @property
    def counts_toward_completion(self) -> bool:
        """Blocked + skipped do not count in the completion-rate denominator."""
        return self.status not in (TaskStatus.blocked, TaskStatus.skipped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "website": self.website, "difficulty": self.difficulty,
            "category": self.category, "executor_mode": self.executor_mode,
            "status": self.status.value, "expect_failure": self.expect_failure,
            "steps_taken": self.steps_taken, "steps_successful": self.steps_successful,
            "steps_failed": self.steps_failed, "human_interventions": self.human_interventions,
            "recoveries_attempted": self.recoveries_attempted,
            "recoveries_successful": self.recoveries_successful,
            "validations_passed": self.validations_passed,
            "validations_failed": self.validations_failed,
            "ai_calls": self.ai_calls, "total_tokens": self.total_tokens,
            "observe_time_ms": round(self.observe_time_ms, 2),
            "analyze_time_ms": round(self.analyze_time_ms, 2),
            "execute_time_ms": round(self.execute_time_ms, 2),
            "validate_time_ms": round(self.validate_time_ms, 2),
            "total_duration_ms": round(self.duration_ms, 2),
            "failure_layer": self.failure_category, "failure_detail": self.failure_detail,
            "final_url": self.final_url,
            "locator_strategies": self.locator_strategy_counts,
            "criteria_results": [c.to_dict() for c in self.criteria_results],
            "steps": [s.to_dict() for s in self.steps],
            "screenshots": self.screenshots, "dom_snapshots": self.dom_snapshots,
            "timeline": self.timeline_path,
        }
