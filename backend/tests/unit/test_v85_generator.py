"""V8.5 Governance Layer — Unit tests: generator.py (14 tests)."""
import time
import pytest
from app.governance.models import GovernanceContract, make_contract
from app.governance import generator as gen
from app.governance import registry as reg
from app.approvals.models import (
    ApprovalStatus, ApprovalRiskLevel, ApprovalSourceType,
    ApprovalRequest, make_approval_request,
)


def _appr(status=ApprovalStatus.approved, risk=ApprovalRiskLevel.high) -> ApprovalRequest:
    a = make_approval_request(
        source_type = ApprovalSourceType.trust_engine,
        source_id   = "src-gen-1",
        title       = "Test Approval",
        description = "test",
        risk_level  = risk,
        priority    = "MEDIUM",
        mission_id  = "m-gen",
        task_id     = "t-gen",
    )
    a.status      = status
    a.resolved_at = time.time()
    a.resolved_by = "tester"
    return a


@pytest.fixture(autouse=True)
def clean():
    reg._reset_for_testing()
    from app.approvals import registry as appr_reg
    appr_reg._reset_for_testing()
    yield
    reg._reset_for_testing()
    from app.approvals import registry as appr_reg2
    appr_reg2._reset_for_testing()


class TestGenerateFromApproval:

    def test_returns_contract_for_approved(self):
        a = _appr(status=ApprovalStatus.approved)
        c = gen.generate_from_approval(a)
        assert c is not None
        assert isinstance(c, GovernanceContract)

    def test_returns_none_for_pending(self):
        a = _appr(status=ApprovalStatus.pending)
        assert gen.generate_from_approval(a) is None

    def test_returns_none_for_rejected(self):
        a = _appr(status=ApprovalStatus.rejected)
        assert gen.generate_from_approval(a) is None

    def test_contract_approved_true(self):
        a = _appr()
        c = gen.generate_from_approval(a)
        assert c.approved is True

    def test_contract_source_type_from_approval(self):
        a = _appr()
        c = gen.generate_from_approval(a)
        assert c.source_type == "TRUST_ENGINE"

    def test_contract_risk_level_from_approval(self):
        a = _appr(risk=ApprovalRiskLevel.critical)
        c = gen.generate_from_approval(a)
        assert c.risk_level == "CRITICAL"

    def test_contract_mission_id_from_approval(self):
        a = _appr()
        c = gen.generate_from_approval(a)
        assert c.mission_id == "m-gen"

    def test_contract_approval_id_from_approval(self):
        a = _appr()
        c = gen.generate_from_approval(a)
        assert c.approval_id == a.approval_id

    def test_contract_execution_allowed(self):
        a = _appr()
        c = gen.generate_from_approval(a)
        assert c.execution_allowed is True


class TestGeneratePendingContractsForMission:

    def test_returns_list(self):
        out = gen.generate_pending_contracts_for_mission("m-gen2")
        assert isinstance(out, list)

    def test_no_duplicates_when_contract_exists(self):
        from app.approvals import registry as appr_reg
        from app.governance import registry as gov_reg
        a = _appr()
        appr_reg.add(a)
        c = gen.generate_from_approval(a)
        gov_reg.add(c)
        # calling again should not create duplicate
        result = gen.generate_pending_contracts_for_mission("m-gen")
        approval_ids = [r.approval_id for r in result]
        assert a.approval_id not in approval_ids

    def test_generates_for_approved_no_contract(self):
        from app.approvals import registry as appr_reg
        a = _appr()
        appr_reg.add(a)
        result = gen.generate_pending_contracts_for_mission("m-gen")
        assert len(result) >= 1

    def test_skips_pending_approvals(self):
        from app.approvals import registry as appr_reg
        a = _appr(status=ApprovalStatus.pending)
        appr_reg.add(a)
        result = gen.generate_pending_contracts_for_mission("m-gen")
        assert len(result) == 0

    def test_graceful_on_missing_mission(self):
        result = gen.generate_pending_contracts_for_mission("no-such-mission")
        assert result == []
