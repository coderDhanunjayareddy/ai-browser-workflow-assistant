from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.schema_validation import SchemaValidator


def main() -> None:
    report = SchemaValidator().compare()
    output = Path(__file__).resolve().parents[1] / ".." / "docs" / "schema_inventory.md"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.to_markdown(), encoding="utf-8")
    print(str(output))


if __name__ == "__main__":
    main()
