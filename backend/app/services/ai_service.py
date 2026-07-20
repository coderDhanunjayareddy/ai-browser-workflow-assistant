import json
import uuid
import re
import time
import os
import base64
import sys
import httpx
import concurrent.futures
from typing import Optional, Dict, Any

from google import genai
from google.genai import types
from google.genai import errors as _genai_errors

from app.core.config import settings
from app.schemas.request import PageContext, PriorStep
from app.schemas.response import AnalyzeResponse, SuggestedAction, ReportOutcome, ReplanOutcome


class TransientAIError(RuntimeError):
    """Raised when the upstream AI service has a retryable transport failure."""


class AIProviderError(RuntimeError):
    """Raised when the configured AI provider returns a non-retryable API error."""

    def __init__(self, provider: str, status_code: int, message: str):
        self.provider = provider
        self.status_code = status_code
        super().__init__(message)


def is_transient_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "server disconnected" in message
        or "connection reset" in message
        or "remote protocol" in message
        or "timeout" in message
        or "temporarily unavailable" in message
        or "connection aborted" in message
        or "read error" in message
    )


def _safe_debug_print(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = str(message).encode(encoding, errors="backslashreplace").decode(
            encoding, errors="replace"
        )
        print(safe, flush=True)


def download_image(url: str) -> tuple[str, bytes, str] | None:
    if url.startswith("data:image"):
        try:
            header, encoded = url.split(",", 1)
            data = base64.b64decode(encoded)
            mime_type = header.split(";")[0].split(":")[1].lower()
            if "svg" in mime_type or "xml" in mime_type:
                return None
            return url, data, mime_type
        except Exception:
            return None
            
    if ".svg" in url.split("?")[0].lower():
        return None
            
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        with httpx.Client(timeout=4.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                mime_type = resp.headers.get("content-type", "image/jpeg").lower()
                if "svg" in mime_type or "xml" in mime_type:
                    return None
                return url, resp.content, mime_type
    except Exception as e:
        _safe_debug_print(f"[Image Downloader] Failed to download {url[:100]}: {e}")
    return None


def download_images_concurrently(urls: list[str], max_images: int = 5) -> list[tuple[str, bytes, str]]:
    results = []
    valid_urls = [u for u in urls if u.startswith("http") or u.startswith("data:image")][:max_images]
    if not valid_urls:
        return []
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(download_image, url): url for url in valid_urls}
        for future in concurrent.futures.as_completed(future_to_url):
            res = future.result()
            if res:
                results.append(res)
    return results


def save_image_locally(url: str, img_bytes: bytes, mime_type: str, index: int) -> str:
    try:
        downloads_dir = "c:/Work/AI_Browser_Assist/downloads"
        os.makedirs(downloads_dir, exist_ok=True)
        ext = "jpg"
        if "png" in mime_type:
            ext = "png"
        elif "webp" in mime_type:
            ext = "webp"
        elif "gif" in mime_type:
            ext = "gif"
        
        filename = f"product_image_{index}.{ext}"
        filepath = os.path.join(downloads_dir, filename)
        with open(filepath, "wb") as f:
            f.write(img_bytes)
        return filepath
    except Exception as e:
        _safe_debug_print(f"[Image Downloader] Failed to save image: {e}")
        return ""


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an AI browser workflow assistant. Decide the NEXT outcome for the user's task — this is not always a browser action.
1. ALWAYS use the exact "selector" value from INTERACTIVE ELEMENTS or VISIBLE CONTENT BLOCKS. NEVER invent selectors. Prefer #id, data-testid, aria-label, title, placeholder, or accessibility-name based selectors.
2. Before choosing a click selector, verify that the same listed element's label, accessibility name, or aria-label matches the control named in your description. Never use a selector whose listed label contradicts the intended control.
3. CURRENT PAGE CONTEXT IS AUTHORITATIVE. Prior steps describe attempts, not guaranteed application state. Never assume that a wait, click, or successful executor result means a destination page loaded. Confirm the expected page using its current URL, heading, visible text, and controls.
4. Suggest only controls that are present in the current INTERACTIVE ELEMENTS. If a login form is still visible, do not propose dashboard, navigation-menu, search-result, or post-login actions. Inspect validation errors and recover the login step first.
5. Produce ONE outcome at a time.
6. If an ACTIVE TASK NODE CONTEXT is provided, satisfy ONLY the current active task node. Do not plan ahead.
7. Output valid JSON in the format:
{
  "analysis": "Brief explanation of this outcome",
  "outcome_kind": "act | report | wait | ask | replan",
  "clarification_question": null,
  "report": null,
  "replan": null,
  "suggested_actions": [
    {
      "action_id": "unique_string",
      "action_type": "click | fill | scroll | navigate | wait | select_option | choose_date | hover | keyboard_shortcut | open_new_tab | switch_tab | close_tab | focus_existing_tab",
      "target_selector": "selector from list",
      "value": "text to type or scroll direction/wait ms",
      "description": "what this does",
      "reasoning": "why this is needed",
      "confidence": 1.0,
      "safety_level": "safe | caution | danger"
    }
  ]
}
8. action_type rules:
- click: target_selector = selector from list, value = null
- fill: target_selector = selector from list, value = text
- select_option: target_selector = select/list/option selector, value = visible option text or option value
- choose_date: target_selector = exact visible date cell/button selector, value = normalized date text
- hover: target_selector = selector from list, value = null
- keyboard_shortcut: target_selector = "window" or focused element selector, value = key such as "Enter" or "Escape"
- scroll: target_selector = "window", value = "up" | "down"
- navigate: target_selector = null, value = URL
- wait: target_selector = "window", value = milliseconds as string
- open_new_tab: target_selector = null, value = explicit http/https URL. Use for research/comparison when preserving the current page helps.
- switch_tab: target_selector = null, value = "tab:<id>", "title:<exact title>", "purpose:<exact purpose>", or "url:<exact URL>" from MULTI-TAB WORKSPACE.
- focus_existing_tab: same as switch_tab, but use when the target tab is already known and should simply become active.
- close_tab: same tab reference format as switch_tab. Use only for clearly safe cleanup; never close pinned, settings, extension, payment, or final tabs.
9. Existing browser execution understands common widgets. For date pickers use choose_date, for comboboxes/custom selects use select_option, for autocomplete use fill or click the matching suggestion, and for cookie banners/modals choose the logical visible control. Do not invent DOM workarounds.
10. File transfer uses normal browser controls. To upload, only when the user explicitly asked and a file input/label/drop zone is visible, use a safe click/fill-style action on that control and never fabricate a local filename. To download, click the visible download/export control; execution records download metadata.
11. Use EXECUTION FEEDBACK when present. If a previous action had no_effect or selector recovery failed, avoid repeating the same selector/action unless current page evidence changed.
12. Use TASK WORKSPACE and MULTI-TAB WORKSPACE when present. Do not navigate redundantly to already-open pages; switch/focus an existing tab when the workspace identifies it.
13. MISSION REVIEW: when Mission Snapshot, Workspace Summary, Tab Workspace, Execution Feedback, Report Validation, Strategy Generation, or Planner Recovery context is present, use the analysis field to reason about mission progress before choosing the next outcome. Do not add new top-level JSON fields. Account for:
- Completed Objectives: treat completed objectives as immutable unless current page evidence clearly contradicts them. Do not reopen, re-search, or repeat already completed work.
- Remaining Objectives and Current Focus: advance to the next remaining objective or subgoal instead of restarting the workflow.
- Evidence Available: if enough evidence exists to answer the user goal or current subgoal, prefer extraction or summarization with outcome_kind "report" instead of unnecessary navigation.
- Evidence Missing: if the mission is incomplete, choose the next action that gathers the missing evidence rather than reporting prematurely.
- Previous Action Result: if execution feedback says no_effect, semantic_mismatch, recovery_failed, or repeated_failure, do not repeat the same selector/action unless the observation changed.
- Loop Prevention: if the same action, report, or wait would repeat without new evidence, choose a different valid outcome or action.
- Mission Completion: when all objectives are complete and the evidence supports the requested answer, finish with outcome_kind "report" and no suggested_actions.
14. MISSION OPERATING MODE: before every outcome, decide the current mode in the analysis field: SEARCH, COLLECT, EXTRACT, VERIFY, COMPARE, or REPORT. Explain why that mode fits and what evidence is required before changing modes. Use SEARCH to locate authoritative sources, COLLECT to open relevant pages, EXTRACT to capture visible requested information immediately, VERIFY to check sufficiency, COMPARE to organize multiple entities, and REPORT to stop browsing and answer. Do not remain in SEARCH or COLLECT once sufficient evidence exists.
15. DOMAIN AND CAPABILITY REASONING: before proposing a browser action, determine the user's actual goal, the capability required, whether the current website can realistically satisfy that capability, and whether a more appropriate application or authoritative source should be used. Stay when the site can satisfy the goal; search or navigate elsewhere when it cannot; report impossibility when the requested action cannot be done on the current site or available sources. Examples: messaging applications are not music platforms; official product pages are authoritative for pricing; search engines are discovery mechanisms; documentation research should prefer official docs; job searches should prefer job platforms and reuse authenticated sessions when available. Continuously re-evaluate website suitability as the workflow progresses.
16. Keep descriptions concise, but do not omit necessary values such as field purpose, date, recipient, search query, tab reference, URL, or option text.
17. outcome_kind chooses the shape of this turn — pick the one that actually matches what is needed, do not default to "act" out of habit:
- "act": suggested_actions has exactly one entry, following rule 8. Use this when a browser interaction is genuinely required.
- "report": the task (or its current active node) is already answerable from PAGE CONTEXT, VISIBLE CONTENT BLOCKS, or CURRENT VERIFIED STATE FACTS as they stand right now — e.g. a price, a name, a status that is already present as text or an accessibility name. Do NOT click an element merely to "reveal" a value that is already present in front of you. suggested_actions must be empty; set "report": {"answer": "the extracted value, if any", "claim": "why you believe the goal is satisfied"}. Never put "report" in suggested_actions.action_type; it is an outcome_kind, not a browser action.
- "wait": the page is mid-transition (e.g. just navigated or an async region is loading) and needs time before the next observation is meaningful. suggested_actions has one entry with action_type "wait" (rule 8).
- "ask": the task cannot proceed without information only the user can supply (e.g. login credentials, a payment choice, an ambiguous preference). suggested_actions must be empty; set "clarification_question" to the question. Never use "ask" to request browser strategy or extraction help — figure those out yourself.
- "replan": the current approach is not working and a different strategy is needed. suggested_actions must be empty; set "replan": {"reason": "why this approach should change"}."""


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_user_message(
    task: str,
    page_context_text: str,
    prior_steps_text: str = "",
    supplemental_context: str = "",
    active_node_text: str = "",
    verified_state_text: str = "",
) -> str:
    msg = f"TASK: {task}\n\nPAGE CONTEXT:\n{page_context_text}"
    if active_node_text:
        msg += f"\n\nACTIVE TASK NODE CONTEXT:\n{active_node_text}"
    if verified_state_text:
        msg += f"\n\nCURRENT VERIFIED STATE FACTS:\n{verified_state_text}"
    if supplemental_context:
        msg += f"\n\nSUPPLEMENTAL CONTEXT:\n{supplemental_context[:3000]}"
    if prior_steps_text:
        msg += f"\n\n{prior_steps_text}"
    return msg


def estimate_tokens(text: str) -> int:
    """Conservative provider-neutral estimate used until exact usage is available."""
    return max(1, (len(text) + 3) // 4)


def selected_provider() -> str:
    provider = (settings.ai_provider or "").strip().lower()
    if provider:
        return provider
    if settings.openrouter_api_key:
        return "openrouter"
    return "gemini"


def _openrouter_headers() -> dict[str, str]:
    api_key = (settings.openrouter_api_key or "").strip()
    if not api_key or api_key == "your-openrouter-api-key":
        raise ValueError("OPENROUTER_API_KEY is not configured")

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_site_url,
        "X-Title": settings.openrouter_app_name,
    }


def _anthropic_headers() -> dict[str, str]:
    api_key = (settings.anthropic_api_key or "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured")

    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


def _extract_provider_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or response.reason_phrase

    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    if error:
        return str(error)
    return response.text or response.reason_phrase


def _call_openrouter_chat(
    messages: list[dict],
    *,
    response_format: dict | None = None,
    max_tokens: int = 512,
) -> str:
    body = {
        "model": settings.openrouter_model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if response_format:
        body["response_format"] = response_format

    _t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=_openrouter_headers(),
                json=body,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        message = _extract_provider_error(exc.response)
        if status_code == 429 or status_code >= 500:
            raise TransientAIError(message) from exc
        raise AIProviderError("OpenRouter", status_code, message) from exc
    except httpx.HTTPError as exc:
        raise TransientAIError(str(exc)) from exc

    payload = response.json()
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIProviderError("OpenRouter", 502, f"Unexpected OpenRouter response: {payload}") from exc

    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    else:
        text = str(content or "")

    # M0.6 diagnostics (TRACE_MODE only): record the exact prompt + raw response. Purely
    # additive; the returned value is unchanged, so behavior is byte-identical when off.
    if settings.trace_mode:
        try:
            from app.diagnostics import trace_sink
            _choice0 = (payload.get("choices") or [{}])[0]
            trace_sink.record_provider_exchange(
                request={"provider": "openrouter", "model": body["model"],
                         "messages": body["messages"], "temperature": body["temperature"],
                         "max_tokens": body["max_tokens"],
                         "response_format": body.get("response_format")},
                response={"raw_text": text, "finish_reason": _choice0.get("finish_reason"),
                          "usage": payload.get("usage")},
                latency_ms=(time.perf_counter() - _t0) * 1000)
        except Exception:
            pass

    return text


def _call_anthropic_messages(
    messages: list[dict],
    *,
    system_prompt: str | None = None,
    max_tokens: int = 512,
) -> str:
    model = settings.anthropic_model
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if _anthropic_accepts_temperature(model):
        body["temperature"] = 0
    if system_prompt:
        body["system"] = system_prompt

    _t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers=_anthropic_headers(),
                json=body,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        message = _extract_provider_error(exc.response)
        if status_code == 429 or status_code >= 500:
            raise TransientAIError(message) from exc
        raise AIProviderError("Anthropic", status_code, message) from exc
    except httpx.HTTPError as exc:
        raise TransientAIError(str(exc)) from exc

    payload = response.json()
    parts = payload.get("content") or []
    text = "".join(
        str(part.get("text", ""))
        for part in parts
        if isinstance(part, dict) and part.get("type") == "text"
    )

    if settings.trace_mode:
        try:
            from app.diagnostics import trace_sink
            trace_sink.record_provider_exchange(
                request={"provider": "anthropic", "model": body["model"],
                         "messages": body["messages"], "system": body.get("system"),
                         "temperature": body.get("temperature"), "max_tokens": body["max_tokens"]},
                response={"raw_text": text, "stop_reason": payload.get("stop_reason"),
                          "usage": payload.get("usage")},
                latency_ms=(time.perf_counter() - _t0) * 1000)
        except Exception:
            pass

    return text


def _anthropic_accepts_temperature(model: str) -> bool:
    """Some latest Anthropic models reject temperature; keep existing behavior elsewhere."""
    return not (model or "").strip().lower().startswith("claude-sonnet-5")


def _image_content_part(img_bytes: bytes, mime_type: str) -> dict:
    encoded = base64.b64encode(img_bytes).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:{mime_type};base64,{encoded}",
        },
    }


def _anthropic_image_content_part(img_bytes: bytes, mime_type: str) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime_type,
            "data": base64.b64encode(img_bytes).decode("ascii"),
        },
    }


# ── Response parser ───────────────────────────────────────────────────────────

def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_object(raw: str) -> str:
    """
    Gemini is asked for JSON, but can still occasionally wrap it in prose,
    markdown fences, or leave trailing commas. Extract the first balanced
    object and normalize common non-JSON comma mistakes before json.loads.
    """
    text = _strip_code_fence(raw)
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", text, 0)

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:index + 1]
                return re.sub(r",\s*([}\]])", r"\1", candidate)

    raise json.JSONDecodeError("Unclosed JSON object", text, start)


def parse_response(raw: str, session_id: str) -> AnalyzeResponse:
    """
    Parse and validate the AI JSON response into an AnalyzeResponse.
    We still validate action types against the allowlist here.
    """
    data = json.loads(_extract_json_object(raw))

    ALLOWED_TYPES = {
        "click",
        "fill",
        "scroll",
        "navigate",
        "wait",
        "select_option",
        "choose_date",
        "hover",
        "keyboard_shortcut",
        "open_new_tab",
        "switch_tab",
        "close_tab",
        "focus_existing_tab",
    }
    ALLOWED_SAFETY = {"safe", "caution", "danger"}

    def safety_from_action(item: dict) -> str:
        supplied = item.get("safety_level", "safe")
        safety = supplied if supplied in ALLOWED_SAFETY else "caution"
        text = " ".join(
            str(item.get(key) or "")
            for key in ("action_type", "target_selector", "value", "description", "reasoning")
        ).lower()

        danger_phrases = (
            "pay now",
            "place order",
            "confirm booking",
            "complete booking",
            "buy now",
            "purchase",
            "delete account",
            "delete permanently",
            "publish",
            "send email",
            "send message",
        )
        caution_phrases = (
            "add to cart",
            "checkout",
            "proceed to payment",
            "compose",
            "fill",
            "submit",
            "book ticket",
            "reserve",
        )

        if any(phrase in text for phrase in danger_phrases):
            return "danger"
        if safety == "safe" and any(phrase in text for phrase in caution_phrases):
            return "caution"
        return safety

    def is_invalid_clarification(question: str | None) -> bool:
        if not question:
            return False
        text = question.lower()

        # clarification_question is reserved for information only the user can
        # provide. If the model asks for browser strategy, extraction help, or a
        # comparison/search decision, suppress it and keep the workflow moving.
        invalid_patterns = (
            "how should i obtain",
            "how would you like me to proceed",
            "would you like me to proceed",
            "would you like to proceed",
            "would you prefer",
            "do you want me to",
            "should i proceed",
            "should i re",
            "should i search",
            "should i use",
            "how should i extract",
            "how to extract",
            "provided interactive elements",
            "do not include selectors",
            "selectors for product",
            "not fully extracted",
            "full comparison",
            "complete comparison",
            "price and rating",
            "prices or ratings",
            "extract product",
            "extract visible",
            "re-search",
            "research on",
            "search again",
            "try again",
            "retry",
            "scroll",
            "open the result",
            "which site",
            "which result",
            "which option",
            "best option",
        )
        user_only_keywords = (
            "login",
            "password",
            "otp",
            "code",
            "email address",
            "phone",
            "address",
            "payment",
            "card",
            "upi",
            "cvv",
            "account",
            "recipient",
            "contact",
            "budget",
            "preference",
            "confirm",
            "confirmation",
        )
        if any(pattern in text for pattern in invalid_patterns):
            return True
        if "would you like" in text and not any(keyword in text for keyword in user_only_keywords):
            return True
        return False

    suggested_raw = data.get("suggested_actions", [])
    if not isinstance(suggested_raw, list):
        suggested_raw = []

    # Planner Contract V2 compatibility: "report" is an outcome kind, not a
    # browser action. If a provider emits the V2 intent in the old action slot,
    # normalize it into the canonical Report outcome before action validation.
    if (suggested_raw and isinstance(suggested_raw[0], dict)
            and suggested_raw[0].get("action_type") == "report"):
        report_action = suggested_raw[0]
        data["outcome_kind"] = "report"
        data["suggested_actions"] = []
        if not isinstance(data.get("report"), dict):
            data["report"] = {
                "answer": report_action.get("value"),
                "claim": (
                    report_action.get("reasoning")
                    or report_action.get("description")
                    or "planner reported the goal is satisfied"
                ),
            }
        suggested_raw = []

    actions: list[SuggestedAction] = []
    for item in suggested_raw[:1]:
        action_type = item.get("action_type", "")
        if action_type not in ALLOWED_TYPES:
            raise ValueError(f"Unsupported action_type from AI: {action_type}")

        safety = safety_from_action(item)

        try:
            confidence = float(item.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.5

        actions.append(
            SuggestedAction(
                action_id=str(item.get("action_id") or uuid.uuid4()),
                action_type=action_type,      # type: ignore[arg-type]
                target_selector=item.get("target_selector") or "",
                value=item.get("value"),
                description=item.get("description", ""),
                reasoning=item.get("reasoning", ""),
                confidence=confidence,
                safety_level=safety,          # type: ignore[arg-type]
            )
        )

    clarification_question = data.get("clarification_question") or None
    if is_invalid_clarification(clarification_question):
        clarification_question = None
        if not actions:
            actions.append(
                SuggestedAction(
                    action_id=str(uuid.uuid4()),
                    action_type="scroll",  # type: ignore[arg-type]
                    target_selector="window",
                    value="down",
                    description="Scroll to reveal more visible listing details.",
                    reasoning=(
                        "The workflow needs page-visible data such as prices or ratings. "
                        "Scrolling can expose more content for extraction; do not ask the user how to extract it."
                    ),
                    confidence=0.6,
                    safety_level="safe",  # type: ignore[arg-type]
                )
            )

    analysis_val = data.get("analysis", "")
    if not isinstance(analysis_val, str):
        analysis_val = json.dumps(analysis_val, indent=2, ensure_ascii=False)

    # Planner Contract V2: which kind of turn this is. Fail open to "act" for any
    # missing/unrecognized value so a non-conforming response degrades to today's
    # behavior rather than erroring.
    ALLOWED_OUTCOME_KINDS = {"act", "report", "wait", "ask", "replan"}
    outcome_kind = data.get("outcome_kind")
    outcome_kind = outcome_kind if outcome_kind in ALLOWED_OUTCOME_KINDS else "act"

    report_obj = None
    report_raw = data.get("report")
    if isinstance(report_raw, dict) and report_raw.get("claim"):
        report_obj = ReportOutcome(answer=report_raw.get("answer"), claim=report_raw["claim"])

    replan_obj = None
    replan_raw = data.get("replan")
    if isinstance(replan_raw, dict) and replan_raw.get("reason"):
        replan_obj = ReplanOutcome(reason=replan_raw["reason"])

    return AnalyzeResponse(
        session_id=session_id,
        analysis=analysis_val,
        outcome_kind=outcome_kind,
        clarification_question=clarification_question,
        suggested_actions=actions,
        report=report_obj,
        replan=replan_obj,
    )


def fallback_parse_failure(session_id: str) -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id=session_id,
        analysis=(
            "The AI returned an invalid structured response. This is recoverable; "
            "retrying from the current page should continue the workflow."
        ),
        clarification_question="The AI response was invalid. Click Continue to retry from the current page.",
        suggested_actions=[],
    )


# ── M1.3 — Reflection (capability spec: docs/m1-engineering-spec.md Part 6) ────
#
# Mechanism decision (Part 10, M1.3 step 2 — recorded here, not assumed in advance):
# a BOUNDED SECONDARY CALL, gated on the Part 6 trigger condition, was chosen over
# extending the primary pass. Reasoning: the trigger condition is defined over the
# *candidate action* the primary call returns — it cannot be evaluated before that
# candidate exists, so "extend the primary pass" cannot act on a verified match, only
# a speculative one. A secondary call gated on the verified match cleanly satisfies
# every Part 6 guarantee: bounded (at most one extra call), fails safe (falls back to
# the original action on any error), no parallel planner (exactly one action is still
# returned), and zero cost on the non-triggered path (the gate is a cheap, local,
# deterministic check with no LLM call of its own).
#
# Evaluation basis (Part 10, M1.3 step 1): no live benchmark run was available when
# this was implemented (see the M1.3 deliverable). The decision instead uses the
# existing evidence trail (M0.7-M0.9, M1.1/M1.2 test results): fixture__login_form's
# repeat is expected to be substantially resolved by M1.1 (episodic memory) + M1.2
# (observable field values) alone, since both signals now independently indicate the
# field is filled. fixture__pagination has no equivalent "is the goal state visible"
# shortcut and M0.9's own scenario analysis (Task 4, scenario 3) predicts memory alone
# is insufficient — reflection is the milestone expected to move that case. This is a
# reasoned evaluation, not a fresh measurement; a live confirmatory run remains pending.

def _detect_repeat_trigger(response: AnalyzeResponse, compressed_context: Optional[dict]) -> Optional[dict]:
    """
    Part 6 trigger condition: does the primary candidate action's (action_type,
    target_selector) match a `recent_actions` entry whose page_changed is False or
    unknown (None)? Pure and deterministic — no LLM call, no side effects. Returns the
    matching entry, or None if reflection is not warranted for this response.
    """
    if not compressed_context or not response.suggested_actions:
        return None
    recent_actions = compressed_context.get("recent_actions") or []
    if not recent_actions:
        return None
    candidate = response.suggested_actions[0]
    if not candidate.target_selector:
        return None
    for entry in recent_actions:
        if not isinstance(entry, dict):
            continue
        if entry.get("action_type") != candidate.action_type:
            continue
        if entry.get("selector") != candidate.target_selector:
            continue
        if entry.get("page_changed") is not True:
            return entry
    return None


def _reflection_directive(matched_entry: dict) -> str:
    """A short instruction referencing the SPECIFIC abandoned action (Part 6 Purpose)."""
    action_type = matched_entry.get("action_type") or "action"
    selector = matched_entry.get("selector") or "the same element"
    return (
        "\n\nREFLECTION: You already attempted this exact action "
        f'({action_type} on selector "{selector}") and it did not produce visible '
        "progress toward the goal. Do not propose that exact action again. Choose a "
        "different element or a different approach, or if repeating it is genuinely "
        "still correct, say so explicitly in your reasoning."
    )


# ── Public interface ──────────────────────────────────────────────────────────

def generate_text(system_prompt: str, user_message: str) -> str:
    """
    Call the configured AI provider in text mode and return a raw string.
    Used by the light assist path (summarization, Q&A).
    Reuses provider selection, retry loop, and error handling from the existing paths.
    """
    provider = selected_provider()

    if provider == "openrouter":
        return _call_openrouter_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1024,
        )

    if provider == "anthropic":
        return _call_anthropic_messages(
            [{"role": "user", "content": user_message}],
            system_prompt=system_prompt,
            max_tokens=1024,
        )

    if provider != "gemini":
        raise ValueError(f"Unsupported AI_PROVIDER={settings.ai_provider}")
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=settings.gemini_api_key)
    contents = [types.Part.from_text(text=user_message)]

    response = None
    last_error = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0,
                ),
            )
            break
        except _genai_errors.APIError as exc:
            status_code = getattr(exc, "code", None) or 502
            raise AIProviderError(
                "Gemini", status_code, str(getattr(exc, "message", None) or exc)
            ) from exc
        except Exception as exc:
            last_error = exc
            transient = is_transient_error(exc)
            if not transient or attempt == 2:
                if transient:
                    raise TransientAIError(str(exc)) from exc
                raise
            time.sleep(1.5 * (attempt + 1))

    if response is None:
        raise last_error or RuntimeError("Gemini did not return a response")

    return response.text or ""


def analyze(
    session_id: str,
    task: str,
    page_context: PageContext,
    prior_steps: list[PriorStep] | None = None,
    supplemental_context: str = "",
    active_node: Optional[Any] = None,
    verified_state: Optional[Dict[str, Any]] = None,
    compressed_context: Optional[Dict[str, Any]] = None,
) -> AnalyzeResponse:
    """
    Call the configured AI provider and return a validated AnalyzeResponse.
    Raises exceptions on API errors so the HTTP route can map them.
    """
    from app.services.context_service import format_page_context, format_prior_steps
    page_context_text = format_page_context(page_context)
    prior_steps_text = format_prior_steps(prior_steps) if prior_steps else ""

    active_node_text = ""
    if active_node:
        active_node_text = f"Node ID: {active_node.node_id}\nDescription: {active_node.description}"

    verified_state_text = ""
    if verified_state:
        verified_state_text = json.dumps(verified_state, indent=2)

    if compressed_context is not None:
        # Interactive planning receives no full DOM/tree/replay. The five-key
        # contract keeps planner input stable and auditable.
        user_message = "COMPRESSED PLANNER CONTEXT:\n" + json.dumps(compressed_context, ensure_ascii=False)
    else:
        user_message = build_user_message(
            task=task,
            page_context_text=page_context_text,
            prior_steps_text=prior_steps_text,
            supplemental_context=supplemental_context,
            active_node_text=active_node_text,
            verified_state_text=verified_state_text,
        )
    provider = selected_provider()

    is_extraction_task = any(k in task.lower() for k in ["extraction agent", "extract all", "structured json", "section 10", "product details", "output format", "section 19"])

    if is_extraction_task:
        _safe_debug_print(f"[AI Service] Detected extraction task. Using {provider} direct text generation mode.")
        # Download images concurrently and save them locally
        downloaded = []
        saved_images_info = []
        if page_context.images:
            _safe_debug_print("[AI Service] Downloading and saving up to 5 images for visual analysis...")
            downloaded = download_images_concurrently(page_context.images, max_images=5)
            for i, (original_url, img_bytes, mime_type) in enumerate(downloaded, 1):
                local_path = save_image_locally(original_url, img_bytes, mime_type, i)
                if local_path:
                    _safe_debug_print(f"[AI Service] Saved image {i} to {local_path}")
                    saved_images_info.append({
                        "url": original_url,
                        "local_path": local_path
                    })

        # Inform Gemini of the exact downloaded images and their local paths
        if saved_images_info:
            user_message += "\n\n" + (
                "DOWNLOADED IMAGES FOR ANALYSIS:\n"
                "The following images have been successfully downloaded and saved to disk. "
                "You MUST use these exact local paths in the image URL lists of your output:\n"
            )
            for info in saved_images_info:
                user_message += f"- URL: {info['url']}\n  Local Path: {info['local_path']}\n"

        if provider == "openrouter":
            content = [{"type": "text", "text": user_message}]
            for _, img_bytes, mime_type in downloaded:
                content.append(_image_content_part(img_bytes, mime_type))

            raw_text = _call_openrouter_chat(
                [{"role": "user", "content": content}],
                max_tokens=2048,
            )
            _safe_debug_print(f"[AI Service] Raw text response from OpenRouter (Extraction):\n{raw_text[:300]}...\n")

            cleaned_text = raw_text.strip()
            if cleaned_text.startswith("```"):
                cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text, flags=re.IGNORECASE)
                cleaned_text = re.sub(r"\s*```$", "", cleaned_text)
                cleaned_text = cleaned_text.strip()

            return AnalyzeResponse(
                session_id=session_id,
                analysis=cleaned_text,
                clarification_question=None,
                suggested_actions=[],
            )

        if provider == "anthropic":
            content = [{"type": "text", "text": user_message}]
            for _, img_bytes, mime_type in downloaded:
                content.append(_anthropic_image_content_part(img_bytes, mime_type))

            raw_text = _call_anthropic_messages(
                [{"role": "user", "content": content}],
                max_tokens=2048,
            )
            _safe_debug_print(f"[AI Service] Raw text response from Anthropic (Extraction):\n{raw_text[:300]}...\n")

            cleaned_text = raw_text.strip()
            if cleaned_text.startswith("```"):
                cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text, flags=re.IGNORECASE)
                cleaned_text = re.sub(r"\s*```$", "", cleaned_text)
                cleaned_text = cleaned_text.strip()

            return AnalyzeResponse(
                session_id=session_id,
                analysis=cleaned_text,
                clarification_question=None,
                suggested_actions=[],
            )

        if provider != "gemini":
            raise ValueError(f"Unsupported AI_PROVIDER={settings.ai_provider}")
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not configured")

        client = genai.Client(api_key=settings.gemini_api_key)

        # Build multimodal content list
        contents = []
        for _, img_bytes, mime_type in downloaded:
            contents.append(
                types.Part.from_bytes(
                    data=img_bytes,
                    mime_type=mime_type
                )
            )
        contents.append(types.Part.from_text(text=user_message))

        # For custom extraction tasks, we generate raw text directly from the model to avoid
        # escaping massive JSON structures inside a JSON string attribute.
        response = None
        last_error = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=settings.gemini_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0,
                    ),
                )
                break
            except Exception as exc:
                last_error = exc
                transient = is_transient_error(exc)
                if not transient or attempt == 2:
                    if transient:
                        raise TransientAIError(str(exc)) from exc
                    raise
                time.sleep(1.5 * (attempt + 1))

        if response is None:
            raise last_error or RuntimeError("Gemini did not return a response")

        raw_text = response.text or ""
        _safe_debug_print(f"[AI Service] Raw text response from Gemini (Extraction):\n{raw_text[:300]}...\n")
        
        # Strip markdown fences if Gemini wrapped it, to keep it clean in the text editor
        cleaned_text = raw_text.strip()
        if cleaned_text.startswith("```"):
            cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r"\s*```$", "", cleaned_text)
            cleaned_text = cleaned_text.strip()

        return AnalyzeResponse(
            session_id=session_id,
            analysis=cleaned_text,
            clarification_question=None,
            suggested_actions=[],
        )

    # Standard browser interactive workflow (JSON mode with SYSTEM_PROMPT)
    # We do NOT download or pass image bytes here to keep request payload tiny and fast.
    _safe_debug_print(f"[AI Service] Standard workflow task via {provider}. Skipping image downloader.")

    if provider == "openrouter":
        raw = _call_openrouter_chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            max_tokens=512,
        )
        _safe_debug_print(f"[AI Service] Raw JSON response from OpenRouter (Workflow):\n{raw}\n")
        for repair_attempt in range(2):
            try:
                result = parse_response(raw, session_id)
                trigger = _detect_repeat_trigger(result, compressed_context)
                if trigger is None:
                    return result
                # M1.3: bounded, fail-safe reflection — one extra call, only when the
                # primary candidate repeats a recent no-progress action (Part 6).
                try:
                    reflected_raw = _call_openrouter_chat(
                        [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_message + _reflection_directive(trigger)},
                        ],
                        response_format={"type": "json_object"},
                        max_tokens=512,
                    )
                    _safe_debug_print(f"[AI Service] M1.3 reflection triggered; raw reflected response:\n{reflected_raw}\n")
                    return parse_response(reflected_raw, session_id)
                except Exception as reflect_err:
                    _safe_debug_print(f"[AI Service] M1.3 reflection call failed, keeping original action: {reflect_err}")
                    return result
            except Exception as e:
                try:
                    with open("debug_openrouter_raw.json", "w", encoding="utf-8") as f:
                        f.write(f"Error: {str(e)}\n\nRaw:\n{raw}")
                except Exception:
                    pass
                _safe_debug_print(f"[AI Service ERROR] OpenRouter parse attempt {repair_attempt} failed: {e}")
                if not isinstance(e, json.JSONDecodeError):
                    raise
                raw = _call_openrouter_chat(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                f"{user_message}\n\nYour previous response was invalid JSON. "
                                "Return only one valid JSON object matching the required output format."
                            ),
                        },
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=512,
                )

        return fallback_parse_failure(session_id)

    if provider == "anthropic":
        raw = _call_anthropic_messages(
            [{"role": "user", "content": user_message}],
            system_prompt=SYSTEM_PROMPT,
            max_tokens=512,
        )
        _safe_debug_print(f"[AI Service] Raw JSON response from Anthropic (Workflow):\n{raw}\n")
        for repair_attempt in range(2):
            try:
                result = parse_response(raw, session_id)
                trigger = _detect_repeat_trigger(result, compressed_context)
                if trigger is None:
                    return result
                try:
                    reflected_raw = _call_anthropic_messages(
                        [{"role": "user", "content": user_message + _reflection_directive(trigger)}],
                        system_prompt=SYSTEM_PROMPT,
                        max_tokens=512,
                    )
                    _safe_debug_print(f"[AI Service] M1.3 reflection triggered; raw reflected response:\n{reflected_raw}\n")
                    return parse_response(reflected_raw, session_id)
                except Exception as reflect_err:
                    _safe_debug_print(f"[AI Service] M1.3 reflection call failed, keeping original action: {reflect_err}")
                    return result
            except Exception as e:
                try:
                    with open("debug_anthropic_raw.json", "w", encoding="utf-8") as f:
                        f.write(f"Error: {str(e)}\n\nRaw:\n{raw}")
                except Exception:
                    pass
                _safe_debug_print(f"[AI Service ERROR] Anthropic parse attempt {repair_attempt} failed: {e}")
                if not isinstance(e, json.JSONDecodeError):
                    raise
                raw = _call_anthropic_messages(
                    [
                        {
                            "role": "user",
                            "content": (
                                f"{user_message}\n\nYour previous response was invalid JSON. "
                                "Return only one valid JSON object matching the required output format."
                            ),
                        },
                    ],
                    system_prompt=SYSTEM_PROMPT,
                    max_tokens=512,
                )

        return fallback_parse_failure(session_id)

    if provider != "gemini":
        raise ValueError(f"Unsupported AI_PROVIDER={settings.ai_provider}")
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=settings.gemini_api_key)
    contents = [types.Part.from_text(text=user_message)]

    response = None
    last_error = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            break
        except Exception as exc:
            last_error = exc
            transient = is_transient_error(exc)
            if not transient or attempt == 2:
                if transient:
                    raise TransientAIError(str(exc)) from exc
                raise
            time.sleep(1.5 * (attempt + 1))

    if response is None:
        raise last_error or RuntimeError("Gemini did not return a response")

    raw = response.text or "{}"
    if settings.trace_mode:
        try:
            from app.diagnostics import trace_sink
            trace_sink.record_provider_exchange(
                request={"provider": "gemini", "model": settings.gemini_model,
                         "messages": [{"role": "user", "content": user_message}],
                         "system": SYSTEM_PROMPT, "temperature": 0, "max_tokens": None,
                         "response_format": {"type": "json_object"}},
                response={"raw_text": raw, "finish_reason": None, "usage": None},
                latency_ms=0.0)
        except Exception:
            pass
    _safe_debug_print(f"[AI Service] Raw JSON response from Gemini (Workflow):\n{raw}\n")
    for repair_attempt in range(2):
        try:
            result = parse_response(raw, session_id)
            trigger = _detect_repeat_trigger(result, compressed_context)
            if trigger is None:
                return result
            # M1.3: bounded, fail-safe reflection — one extra call, only when the
            # primary candidate repeats a recent no-progress action (Part 6).
            try:
                reflected_response = client.models.generate_content(
                    model=settings.gemini_model,
                    contents=contents + [types.Part.from_text(text=_reflection_directive(trigger))],
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        temperature=0,
                    ),
                )
                reflected_raw = reflected_response.text or "{}"
                if settings.trace_mode:
                    try:
                        from app.diagnostics import trace_sink
                        trace_sink.record_provider_exchange(
                            request={"provider": "gemini", "model": settings.gemini_model,
                                     "messages": [
                                         {"role": "user", "content": user_message},
                                         {"role": "user", "content": _reflection_directive(trigger)},
                                     ],
                                     "system": SYSTEM_PROMPT, "temperature": 0, "max_tokens": None,
                                     "response_format": {"type": "json_object"}},
                            response={"raw_text": reflected_raw, "finish_reason": None, "usage": None},
                            latency_ms=0.0)
                    except Exception:
                        pass
                _safe_debug_print(f"[AI Service] M1.3 reflection triggered; raw reflected response:\n{reflected_raw}\n")
                return parse_response(reflected_raw, session_id)
            except Exception as reflect_err:
                _safe_debug_print(f"[AI Service] M1.3 reflection call failed, keeping original action: {reflect_err}")
                return result
        except Exception as e:
            try:
                with open("debug_gemini_raw.json", "w", encoding="utf-8") as f:
                    f.write(f"Error: {str(e)}\n\nRaw:\n{raw}")
            except Exception:
                pass
            _safe_debug_print(f"[AI Service ERROR] parse attempt {repair_attempt} failed: {e}")
            if not isinstance(e, json.JSONDecodeError):
                raise
            repair_response = client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            raw = repair_response.text or "{}"
            if settings.trace_mode:
                try:
                    from app.diagnostics import trace_sink
                    trace_sink.record_provider_exchange(
                        request={"provider": "gemini", "model": settings.gemini_model,
                                 "messages": [{"role": "user", "content": user_message}],
                                 "system": SYSTEM_PROMPT, "temperature": 0, "max_tokens": None,
                                 "response_format": {"type": "json_object"}},
                        response={"raw_text": raw, "finish_reason": None, "usage": None},
                        latency_ms=0.0)
                except Exception:
                    pass

    return fallback_parse_failure(session_id)
