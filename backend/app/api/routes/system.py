from __future__ import annotations

from fastapi import APIRouter, Response

from app.schema_validation import SchemaValidator


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/schema")
def schema() -> dict:
    return SchemaValidator().compare().to_dict()


@router.get("/schema/drift")
def schema_drift() -> dict:
    report = SchemaValidator().compare()
    return {
        "compatible": report.compatible,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "comparisons": [
            item.to_dict()
            for item in report.comparisons
            if item.status != "MATCH"
        ],
    }


@router.get("/schema/report")
def schema_report() -> Response:
    return Response(SchemaValidator().compare().to_markdown(), media_type="text/markdown")
