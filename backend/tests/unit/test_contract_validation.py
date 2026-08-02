from __future__ import annotations

from app.contracts.validator import ContractValidator


def test_contract_validator_generates_hashes_for_core_contracts():
    statuses = ContractValidator().validate()

    assert statuses
    assert all(item.compatible for item in statuses)
    assert {"mission_result.result", "mission_ledger.intent_dto", "extension_api.analyze_response"} <= {
        item.name for item in statuses
    }
    assert all(item.schema_hash for item in statuses)
