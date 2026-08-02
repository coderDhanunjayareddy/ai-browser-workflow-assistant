# Infrastructure Validation

## Commands

```bash
cd backend
alembic upgrade head
python scripts/schema_inventory.py
python scripts/infrastructure_check.py
python -m pytest tests/unit/test_schema_validation.py tests/unit/test_contract_validation.py tests/unit/test_serialization_roundtrip.py -q
```

## Checks

- Alembic head is reachable.
- Database revision matches Alembic head.
- ORM and PostgreSQL schema are compared.
- Contract schemas produce stable hashes.
- Serialization round trips preserve payloads.
- Known drift is captured by migration `20260802_0002`.

## CI Policy

CI should fail when:

- Alembic migration state is not at head.
- Schema drift contains `ERROR`.
- Contract validation reports incompatible contracts.
- Serialization round-trip tests fail.
- Migration upgrade fails.

Downgrade checks should run for reversible migrations. Baseline downgrade is non-destructive by design.
