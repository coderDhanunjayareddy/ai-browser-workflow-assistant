from benchmark.goal_convergence import ConvergenceEvidence, GoalConvergenceEngine


def evidence(
    *,
    outcome_kind: str = "report",
    strategy_key: str = "report",
    semantic_signature: str = "page-a",
    validation_signature: str = "missing-price",
    verified: bool = False,
) -> ConvergenceEvidence:
    return ConvergenceEvidence(
        outcome_kind=outcome_kind,
        strategy_key=strategy_key,
        semantic_signature=semantic_signature,
        validation_signature=validation_signature,
        verified=verified,
    )


def test_repeated_unsupported_reports_trigger_replan():
    engine = GoalConvergenceEngine()

    assert not engine.assess(evidence()).should_replan
    decision = engine.assess(evidence())

    assert decision.should_replan
    assert "repeated report" in decision.reason


def test_repeated_identical_actions_with_unchanged_semantic_evidence_trigger_replan():
    engine = GoalConvergenceEngine()
    ev = evidence(
        outcome_kind="click",
        strategy_key="click|#next|",
        semantic_signature="same-page",
        validation_signature="same-failure",
    )

    assert not engine.assess(ev).should_replan
    assert engine.assess(ev).should_replan


def test_semantic_progress_resets_convergence_state():
    engine = GoalConvergenceEngine()

    assert not engine.assess(evidence(semantic_signature="page-a")).should_replan
    assert not engine.assess(evidence(semantic_signature="page-b")).should_replan
    assert not engine.assess(evidence(semantic_signature="page-a")).should_replan


def test_successful_semantic_progress_continues_normally():
    engine = GoalConvergenceEngine()

    first = evidence(
        outcome_kind="fill",
        strategy_key="fill|#q|camera",
        semantic_signature="search-form",
        validation_signature="query-missing",
    )
    second = evidence(
        outcome_kind="fill",
        strategy_key="fill|#q|camera",
        semantic_signature="query-filled",
        validation_signature="results-missing",
    )

    assert not engine.assess(first).should_replan
    assert not engine.assess(second).should_replan


def test_verified_completion_resets_and_never_replans():
    engine = GoalConvergenceEngine()

    assert not engine.assess(evidence()).should_replan
    assert not engine.assess(evidence(verified=True)).should_replan
    assert not engine.assess(evidence()).should_replan
