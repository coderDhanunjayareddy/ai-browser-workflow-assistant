from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


DEFAULT_RESEARCH_FIELDS = ["tool", "purpose", "pricing", "limitation", "url"]


@dataclass(frozen=True)
class ResearchMissionSpec:
    objective: str
    query: str
    source_count: int
    source_policy: str
    required_fields: list[str]
    output_format: Literal["markdown", "json", "csv"]
    artifact_type: Literal["comparison_table", "summary", "json", "csv"]
    completion_criteria: list[str]
    evidence_requirements: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_research_mission_spec(task: str) -> ResearchMissionSpec | None:
    if not is_research_mission(task):
        return None
    fields = _explicit_fields(task) or list(DEFAULT_RESEARCH_FIELDS)
    source_count = _source_count(task)
    output_format = _output_format(task)
    artifact_type: Literal["comparison_table", "summary", "json", "csv"] = "comparison_table"
    if output_format == "json":
        artifact_type = "json"
    elif output_format == "csv":
        artifact_type = "csv"
    elif len(fields) <= 2:
        artifact_type = "summary"
    query = _query(task)
    return ResearchMissionSpec(
        objective=task.strip(),
        query=query,
        source_count=source_count,
        source_policy="distinct_non_search_source_urls",
        required_fields=fields,
        output_format=output_format,
        artifact_type=artifact_type,
        completion_criteria=[
            f"at_least_{source_count}_distinct_source_records",
            "all_required_fields_present_or_explicitly_not_mentioned",
            "each_record_has_source_url",
            "final_artifact_generated_from_extraction_records",
        ],
        evidence_requirements=[
            {
                "evidence_kind": "source_page",
                "subject": "distinct_non_search_source_url",
                "cardinality": source_count,
                "required": True,
            },
            {
                "evidence_kind": "extraction_record",
                "subject": ",".join(fields),
                "cardinality": source_count,
                "required": True,
            },
        ],
    )


def is_research_mission(task: str) -> bool:
    text = task.lower()
    return any(term in text for term in ("research", "compare", "comparison", "summarize", "summary", "extract")) and any(
        term in text for term in ("tool", "pricing", "source", "result", "documentation", "browser automation", "job", "company")
    )


def _explicit_fields(task: str) -> list[str]:
    columns_match = re.search(r"columns?\s*:\s*([^.\n]+)", task, flags=re.IGNORECASE)
    if columns_match:
        fields = [_normalize_field(item) for item in re.split(r",|\band\b", columns_match.group(1)) if item.strip()]
        return [field for field in fields if field][:12]
    extract_match = re.search(
        r"extract\s+(.+?)(?:\s+and\s+(?:produce|return|create|generate)|\s+from|\s+with|\s+for|\.|\n|$)",
        task,
        flags=re.IGNORECASE,
    )
    if extract_match:
        fields = [_normalize_field(item) for item in re.split(r",|\band\b", extract_match.group(1)) if item.strip()]
        fields = [field for field in fields if field and field not in {"the", "details", "information"}]
        if len(fields) >= 2:
            return fields[:12]
    return []


def _source_count(task: str) -> int:
    explicit = re.search(r"\btop\s+(\d{1,2})\b|\bfirst\s+(\d{1,2})\b|\b(\d{1,2})\s+(?:relevant\s+)?(?:results|sources|pages|tabs)\b", task, flags=re.IGNORECASE)
    if explicit:
        count = next((int(group) for group in explicit.groups() if group), 0)
        if count:
            return max(1, min(count, 10))
    return 5 if "top" in task.lower() or "first page" in task.lower() else 1


def _output_format(task: str) -> Literal["markdown", "json", "csv"]:
    text = task.lower()
    if "json" in text:
        return "json"
    if "csv" in text:
        return "csv"
    return "markdown"


def _query(task: str) -> str:
    match = re.search(r"search\s+for\s*:?\s*`?([^`.\n]+)", task, flags=re.IGNORECASE)
    if match:
        return " ".join(match.group(1).split())
    quoted = re.search(r"`([^`]+)`|\"([^\"]+)\"", task)
    if quoted:
        return " ".join(next(group for group in quoted.groups() if group).split())
    return ""


def _normalize_field(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
