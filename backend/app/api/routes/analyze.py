import json

from fastapi import APIRouter, HTTPException
from google.genai import errors

from app.core.config import settings
from app.schemas.request import AnalyzeRequest
from app.schemas.response import AnalyzeResponse
from app.services import ai_service, context_service

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Analyze a page context and task. Returns AI-suggested browser actions.
    Each error case maps to a specific HTTP status so the extension can
    show a meaningful message instead of a generic failure.
    """
    page_context_text = context_service.format_page_context(request.page_context)
    
    print("\n================= PAGE CONTEXT =================")
    print(f"URL: {request.page_context.url}")
    print("INTERACTIVE ELEMENTS:")
    for el in request.page_context.interactive_elements[:15]:
        try:
            print(f"- Tag: {el.type} | Text: {el.text} | Selector: {el.selector}")
        except Exception:
            try:
                text_safe = el.text.encode('ascii', errors='replace').decode('ascii') if el.text else ""
                print(f"- Tag: {el.type} | Text: {text_safe} | Selector: {el.selector}")
            except Exception:
                pass
    print("================================================\n", flush=True)

    try:
        return ai_service.analyze(
            session_id=request.session_id,
            task=request.task,
            page_context=request.page_context,
            prior_steps=request.prior_steps or [],
            supplemental_context=request.supplemental_context,
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
