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


def test_click_wait_report_with_unchanged_semantic_evidence_triggers_replan():
    engine = GoalConvergenceEngine()

    click = evidence(
        outcome_kind="click",
        strategy_key="click|#p2|",
        semantic_signature="page-still-one",
        validation_signature="missing-page-two",
    )
    wait = evidence(
        outcome_kind="wait",
        strategy_key="wait|window|2000",
        semantic_signature="page-still-one",
        validation_signature="missing-page-two",
    )
    report = evidence(
        outcome_kind="report",
        strategy_key="report",
        semantic_signature="page-still-one",
        validation_signature="missing-page-two",
    )

    assert not engine.assess(click).should_replan
    assert engine.assess(wait).should_replan
    engine.reset()
    assert not engine.assess(wait).should_replan
    assert engine.assess(report).should_replan


def test_different_semantic_evidence_does_not_trigger_replan_across_actions():
    engine = GoalConvergenceEngine()

    assert not engine.assess(evidence(
        outcome_kind="click",
        strategy_key="click|#next|",
        semantic_signature="page-one",
        validation_signature="missing-target",
    )).should_replan
    assert not engine.assess(evidence(
        outcome_kind="wait",
        strategy_key="wait|window|2000",
        semantic_signature="page-loading",
        validation_signature="missing-target",
    )).should_replan
    assert not engine.assess(evidence(
        outcome_kind="report",
        strategy_key="report",
        semantic_signature="page-two-visible",
        validation_signature="missing-confirmation",
    )).should_replan


def test_genuine_semantic_progress_resets_convergence_across_actions():
    engine = GoalConvergenceEngine()

    assert not engine.assess(evidence(
        outcome_kind="click",
        strategy_key="click|#p2|",
        semantic_signature="page-one",
        validation_signature="missing-page-two",
    )).should_replan
    assert not engine.assess(evidence(
        outcome_kind="wait",
        strategy_key="wait|window|2000",
        semantic_signature="page-two",
        validation_signature="missing-item-c",
    )).should_replan
    assert not engine.assess(evidence(
        outcome_kind="report",
        strategy_key="report",
        semantic_signature="page-two-with-item-c",
        validation_signature="complete",
    )).should_replan


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
