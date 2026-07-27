from app.mission_completion.models import (
    CompletionDecision,
    CriterionEvaluation,
    CriterionKind,
    CompletionStatus,
    MissionPlan,
    MissionCompletionSnapshot,
    MissionSuccessCriterion,
    ObjectiveType,
    ValidationStatus,
    WorkflowResult,
)


def observe_mission_completion(*args, **kwargs):
    from app.mission_completion.engine import observe_mission_completion as _observe_mission_completion

    return _observe_mission_completion(*args, **kwargs)


def enrich_planner_context_with_completion(*args, **kwargs):
    from app.mission_completion.engine import enrich_planner_context_with_completion as _enrich

    return _enrich(*args, **kwargs)


def postprocess_with_mission_completion(*args, **kwargs):
    from app.mission_completion.engine import postprocess_with_mission_completion as _postprocess

    return _postprocess(*args, **kwargs)


def should_terminate_before_planner(*args, **kwargs):
    from app.mission_completion.engine import should_terminate_before_planner as _should_terminate

    return _should_terminate(*args, **kwargs)


def completion_response(*args, **kwargs):
    from app.mission_completion.engine import completion_response as _completion_response

    return _completion_response(*args, **kwargs)


def __getattr__(name: str):
    if name == "MissionCompletionController":
        from app.mission_completion.engine import MissionCompletionController

        return MissionCompletionController
    raise AttributeError(name)


__all__ = [
    "CompletionDecision",
    "CriterionEvaluation",
    "CriterionKind",
    "CompletionStatus",
    "MissionPlan",
    "MissionCompletionController",
    "MissionCompletionSnapshot",
    "MissionSuccessCriterion",
    "ObjectiveType",
    "ValidationStatus",
    "WorkflowResult",
    "completion_response",
    "enrich_planner_context_with_completion",
    "observe_mission_completion",
    "postprocess_with_mission_completion",
    "should_terminate_before_planner",
]
