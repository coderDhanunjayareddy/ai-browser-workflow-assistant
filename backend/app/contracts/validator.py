from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.contracts.registry import CONTRACTS, ContractDescriptor, schema_for, schema_hash


@dataclass(frozen=True)
class ContractStatus:
    name: str
    version: str
    owner: str
    schema_hash: str
    compatible: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "owner": self.owner,
            "schema_hash": self.schema_hash,
            "compatible": self.compatible,
            "detail": self.detail,
        }


class ContractValidator:
    def validate(self, contracts: list[ContractDescriptor] | None = None) -> list[ContractStatus]:
        statuses: list[ContractStatus] = []
        for contract in contracts or CONTRACTS:
            try:
                schema = schema_for(contract.target)
                statuses.append(
                    ContractStatus(
                        name=contract.name,
                        version=contract.version,
                        owner=contract.owner,
                        schema_hash=schema_hash(schema),
                        compatible=True,
                        detail="schema generated",
                    )
                )
            except Exception as exc:
                statuses.append(
                    ContractStatus(
                        name=contract.name,
                        version=contract.version,
                        owner=contract.owner,
                        schema_hash="",
                        compatible=False,
                        detail=str(exc),
                    )
                )
        return statuses
