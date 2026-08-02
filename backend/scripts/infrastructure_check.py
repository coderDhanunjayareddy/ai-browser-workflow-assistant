from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.contracts.validator import ContractValidator
from app.schema_validation import SchemaValidator


def main() -> int:
    schema_report = SchemaValidator().compare()
    contract_statuses = ContractValidator().validate()
    contract_failures = [item for item in contract_statuses if not item.compatible]

    print("Infrastructure Validation")
    print(f"schema_compatible={schema_report.compatible}")
    print(f"schema_errors={schema_report.error_count}")
    print(f"schema_warnings={schema_report.warning_count}")
    print(f"alembic_current={schema_report.alembic_current}")
    print(f"alembic_head={schema_report.alembic_head}")
    print(f"contract_count={len(contract_statuses)}")
    print(f"contract_failures={len(contract_failures)}")

    if not schema_report.compatible or contract_failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
