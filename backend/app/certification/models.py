"""
Phase F — Certification domain models (deterministic dataclasses).

A CertificationScenario declares: website, workflow, expected outcome, success criteria,
supported browser, required authentication, and known limitations. A CertificationResult
is the reproducible outcome of running one scenario. Pure data — no behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class ScenarioCategory(str, Enum):
    form_submit      = "FORM_SUBMIT"
    search           = "SEARCH"
    filter           = "FILTER"
    table_edit       = "TABLE_EDIT"
    upload           = "UPLOAD"
    download         = "DOWNLOAD"
    navigation       = "NAVIGATION"
    dialog           = "DIALOG"
    recovery         = "RECOVERY"
    resume           = "RESUME"
    pagination       = "PAGINATION"
    multistep        = "MULTISTEP"
    tabs             = "TABS"
    accordion        = "ACCORDION"
    dynamic_loading  = "DYNAMIC_LOADING"
    toast            = "TOAST"
    infinite_scroll  = "INFINITE_SCROLL"
    drag_drop        = "DRAG_DROP"


class Browser(str, Enum):
    chromium = "chromium"


class OutcomeStatus(str, Enum):
    passed  = "PASSED"
    failed  = "FAILED"
    skipped = "SKIPPED"
    error   = "ERROR"


class CriterionKind(str, Enum):
    state_completed       = "STATE_COMPLETED"        # ExecutionRecord reached completed
    min_completed_steps   = "MIN_COMPLETED_STEPS"    # >= N steps completed
    post_validation       = "POST_VALIDATION"        # step[i].output.post_validation.passed
    content_contains      = "CONTENT_CONTAINS"       # step[i].output details content_preview contains
    recovery_used         = "RECOVERY_USED"          # step[i] used >= 1 recovery
    bounded_failure       = "BOUNDED_FAILURE"        # failed but attempts <= N (no infinite loop)
    failure_category      = "FAILURE_CATEGORY"       # step[i].output.failure_category == target
    semantic_present      = "SEMANTIC_PRESENT"       # Website Intelligence found a structure type


@dataclass
class SuccessCriterion:
    kind:       CriterionKind
    detail:     str = ""
    step_index: Optional[int] = None
    target:     Optional[str] = None        # type/text/structure to look for
    value:      Optional[int] = None        # numeric bound (min steps, max attempts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind":       self.kind.value,
            "detail":     self.detail,
            "step_index": self.step_index,
            "target":     self.target,
            "value":      self.value,
        }


@dataclass
class CriterionResult:
    kind:     str
    detail:   str
    passed:   bool
    observed: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail, "passed": self.passed, "observed": self.observed}


@dataclass
class CertificationScenario:
    scenario_id:       str
    name:              str
    website:           str                         # logical site name (the fixture)
    workflow:          str                         # human description of the workflow
    category:          ScenarioCategory
    fixture:           str                         # fixture path served by FixtureServer (e.g. "/login")
    expected_outcome:  str
    success_criteria:  list[SuccessCriterion] = field(default_factory=list)
    browser:           Browser = Browser.chromium
    requires_auth:     bool = True                 # the gateway requires authorization (always true here)
    known_limitations: list[str] = field(default_factory=list)
    # build_steps(base_url) -> list[ExecutionStep]; kept as a callable so scenarios are declarative
    build_steps:       Optional[Callable[[str], list]] = None
    expect_failure:    bool = False                # certified NEGATIVE path (bounded failure)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id":       self.scenario_id,
            "name":              self.name,
            "website":           self.website,
            "workflow":          self.workflow,
            "category":          self.category.value,
            "fixture":           self.fixture,
            "expected_outcome":  self.expected_outcome,
            "success_criteria":  [c.to_dict() for c in self.success_criteria],
            "browser":           self.browser.value,
            "requires_auth":     self.requires_auth,
            "known_limitations": self.known_limitations,
            "expect_failure":    self.expect_failure,
        }


@dataclass
class CertificationResult:
    scenario_id:       str
    name:              str
    category:          str
    website:           str
    status:            OutcomeStatus
    execution_state:   Optional[str] = None
    execution_id:      Optional[str] = None
    completed_steps:   int = 0
    total_steps:       int = 0
    duration_ms:       float = 0.0
    criteria:          list[CriterionResult] = field(default_factory=list)
    failure_category:  Optional[str] = None
    failure_detail:    Optional[str] = None
    real_browser:      bool = False

    @property
    def passed(self) -> bool:
        return self.status == OutcomeStatus.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id":      self.scenario_id,
            "name":             self.name,
            "category":         self.category,
            "website":          self.website,
            "status":           self.status.value,
            "passed":           self.passed,
            "execution_state":  self.execution_state,
            "execution_id":     self.execution_id,
            "completed_steps":  self.completed_steps,
            "total_steps":      self.total_steps,
            "duration_ms":      round(self.duration_ms, 3),
            "criteria":         [c.to_dict() for c in self.criteria],
            "failure_category": self.failure_category,
            "failure_detail":   self.failure_detail,
            "real_browser":     self.real_browser,
        }


@dataclass
class WorkflowOutcome:
    """One recorded workflow run, fed to the reliability register."""
    scenario_id: str
    category:    str
    website:     str
    passed:      bool
    duration_ms: float
    real_browser: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id":  self.scenario_id,
            "category":     self.category,
            "website":      self.website,
            "passed":       self.passed,
            "duration_ms":  round(self.duration_ms, 3),
            "real_browser": self.real_browser,
        }
