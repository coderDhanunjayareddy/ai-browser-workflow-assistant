import json

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header, Request
from sqlalchemy.orm import Session
from google.genai import errors

from app.core.config import settings
from app.core.database import get_db
from app.diagnostics.console import diagnostic_terminal_enabled, safe_print
from app.schemas.request import AnalyzeRequest
from app.schemas.response import AnalyzeResponse
from app.services import ai_service, context_service
from app.budget_engine import BudgetExceededError

router = APIRouter()


@router.get("/analyze")
def analyze_usage() -> dict:
    return {
        "endpoint": "/analyze",
        "method": "POST",
        "message": "Send a JSON AnalyzeRequest body with session_id, task, and page_context.",
        "docs": "/docs",
    }


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: Request, payload: AnalyzeRequest, db: Session = Depends(get_db),
            x_trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id")) -> AnalyzeResponse:
    """
    Analyze a page context and task. Returns AI-suggested browser actions.
    Each error case maps to a specific HTTP status so the extension can
    show a meaningful message instead of a generic failure.
    """
    # M0.6 diagnostics (TRACE_MODE only): tag this request so the provider exchange is
    # written under this trace_id. No-op when TRACE_MODE is off; never alters the response.
    if x_trace_id:
        from app.diagnostics import trace_sink
        trace_sink.set_current(x_trace_id)

    await _log_live_path_analyze_receipt(request, payload)

    page_context_text = context_service.format_page_context(payload.page_context)
    
    if diagnostic_terminal_enabled("AI_BROWSER_VERBOSE_TERMINAL"):
        safe_print("\n================= PAGE CONTEXT =================")
        safe_print(f"URL: {payload.page_context.url}")
        safe_print("INTERACTIVE ELEMENTS:")
        for el in payload.page_context.interactive_elements[:15]:
            safe_print(f"- Tag: {el.type} | Text: {el.text} | Selector: {el.selector}")
        safe_print("================================================\n")

    try:
        from app.orchestrator.workflow_orchestrator import WorkflowOrchestrator
        orchestrator = WorkflowOrchestrator(payload.session_id, db)
        return orchestrator.orchestrate_analysis(
            task=payload.task,
            page_context=payload.page_context,
            prior_steps=payload.prior_steps or [],
            supplemental_context=payload.supplemental_context or "",
            handoff_payload=payload.handoff_payload,
        )
    except errors.APIError as e:
        status_code = e.code or 502
        if status_code == 401:
            detail = "Invalid Gemini API key. Check GEMINI_API_KEY in backend/.env"
        elif status_code == 403:
            detail = (
                "Gemini API access was denied for "
                f"GEMINI_MODEL={settings.gemini_model}. Check your account, key, "
                "billing/project access, and model access."
            )
        elif status_code == 429:
            detail = "Gemini rate limit reached. Wait a minute and try again."
        elif status_code >= 500:
            detail = "Gemini API is temporarily unavailable. Try again shortly."
        else:
            detail = f"Gemini API error: {e.message or str(e)}"
        raise HTTPException(status_code=status_code, detail=detail)
    except json.JSONDecodeError:
        return ai_service.fallback_parse_failure(request.session_id)
    except BudgetExceededError as e:
        raise HTTPException(
            status_code=409,
            detail={"status": "BUDGET_EXCEEDED", "reason": e.reason, "budget": e.budget.model_dump(mode="json")},
        )
    except ai_service.AIProviderError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=f"{e.provider} API error: {str(e)}",
        )
    except ai_service.TransientAIError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI service connection was interrupted. Retry the analysis. Details: {str(e)}",
        )
    except Exception as e:
        if ai_service.is_transient_error(e):
            raise HTTPException(
                status_code=503,
                detail=f"AI service connection was interrupted. Retry the analysis. Details: {str(e)}",
            )
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


async def _log_live_path_analyze_receipt(request: Request, payload: AnalyzeRequest) -> None:
    try:
        raw = await request.json()
        raw_page_context = raw.get("page_context", {}) if isinstance(raw, dict) else {}
        raw_keys = list(raw_page_context.keys()) if isinstance(raw_page_context, dict) else []
        raw_semantic_keys = [key for key in raw_keys if any(term in key.lower() for term in ("semantic", "entity", "browser_intelligence", "page_model"))]
        interactive = payload.page_context.interactive_elements
        blocks = payload.page_context.content_blocks
        if not diagnostic_terminal_enabled("AI_BROWSER_LIVE_PATH_TRACE"):
            return
        safe_print(
            "[V4.5.1 live-path] BACKEND_ANALYZE_RECEIVED "
            + json.dumps(
                {
                    "session_id": payload.session_id,
                    "raw_page_context_keys": raw_keys,
                    "raw_semantic_keys": raw_semantic_keys,
                    "validated_page_context_keys": list(payload.page_context.model_dump().keys()),
                    "interactive_count": len(interactive),
                    "content_block_count": len(blocks),
                    "has_raw_semantic_entities": isinstance(raw_page_context, dict) and isinstance(raw_page_context.get("semantic_entities"), list),
                    "raw_semantic_entity_count": len(raw_page_context.get("semantic_entities", [])) if isinstance(raw_page_context, dict) and isinstance(raw_page_context.get("semantic_entities"), list) else 0,
                    "first_interactive": [
                        {
                            "text": item.text,
                            "href": item.href,
                            "semantic_kind": item.semantic_kind,
                            "selector_id": item.selector_id,
                        }
                        for item in interactive[:6]
                    ],
                    "first_content_blocks": [
                        {
                            "text": item.text[:120],
                            "href": item.href,
                            "selector": item.selector,
                        }
                        for item in blocks[:6]
                    ],
                },
                ensure_ascii=True,
            ),
        )
    except Exception as exc:
        safe_print(f"[V4.5.1 live-path] BACKEND_ANALYZE_RECEIPT_LOG_FAILED {exc}")
