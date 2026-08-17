from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.research.providers.duckduckgo import DuckDuckGoProvider
from app.tool_routing import connectors
from app.tool_routing.isolated_browser import run_isolated_research
from app.tool_routing.models import (
    ConnectorCallRequest,
    IsolatedResearchRequest,
    StructuredSearchRequest,
    ToolRoutingRequest,
)
from app.tool_routing.router import route_task
from app.tool_routing.trace_store import get, recent

router = APIRouter(prefix="/tool-routing", tags=["tool-routing"])


@router.post("/route")
def choose_route(request: ToolRoutingRequest) -> dict:
    return route_task(request).model_dump(mode="json")


@router.post("/search")
def structured_search(request: StructuredSearchRequest) -> dict:
    trace = route_task(ToolRoutingRequest(task=request.query, untrusted_research=True))
    if trace.selected_route.value != "structured_search":
        raise HTTPException(status_code=409, detail=trace.model_dump(mode="json"))
    sources = DuckDuckGoProvider().search(request.query, max_results=request.max_results)
    return {
        "trace": trace.model_dump(mode="json"),
        "results": [
            {
                "title": source.title,
                "url": source.url,
                "snippet": source.snippet,
                "source_type": source.source_type.value,
                "credibility_score": source.credibility_score,
            }
            for source in sources
        ],
    }


@router.post("/connector")
def connector_call(request: ConnectorCallRequest) -> dict:
    if not request.read_only:
        raise HTTPException(
            status_code=409,
            detail="Mutating connector operations require a Phase 1 policy decision and explicit approval integration.",
        )
    trace = route_task(ToolRoutingRequest(
        task=f"{request.operation} through {request.connector}",
        connector=request.connector,
        connector_available=connectors.available(request.connector),
    ))
    if trace.selected_route.value != "connector_api":
        raise HTTPException(status_code=409, detail=trace.model_dump(mode="json"))
    try:
        result = connectors.call(request.connector, request.operation, request.arguments)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"trace": trace.model_dump(mode="json"), "result": result}


@router.post("/isolated/research")
def isolated_research(request: IsolatedResearchRequest) -> dict:
    trace = route_task(ToolRoutingRequest(
        task=request.objective,
        requires_dynamic_rendering=True,
        untrusted_research=True,
    ))
    try:
        result = run_isolated_research(request.url, timeout_ms=request.timeout_ms)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Isolated browser failed: {exc}") from exc
    return {"trace": trace.model_dump(mode="json"), "result": result.to_dict()}


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    trace = get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Tool route trace not found")
    return trace.model_dump(mode="json")


@router.get("/traces")
def list_traces(limit: int = Query(default=50, ge=1, le=100)) -> list[dict]:
    return [trace.model_dump(mode="json") for trace in recent(limit)]
