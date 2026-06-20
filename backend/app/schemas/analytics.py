from pydantic import BaseModel


class CostMetrics(BaseModel):
    planner_calls: int = 0
    vision_calls: int = 0
    tokens_used: int = 0
    average_tokens_per_step: float = 0
    average_planning_latency_ms: float = 0


class WorkflowAnalytics(BaseModel):
    session_id: str
    status: str
    budget_usage: dict
    token_usage: int
    recovery_count: int
    failure_types: dict[str, int]
    success_rate: float
    false_success_rate: float
    workflow_stability_score: float
    average_completion_time_seconds: float
    cost_metrics: CostMetrics
