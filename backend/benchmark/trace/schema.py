"""
M0.6 — Versioned trace schema (planner_trace_v1).

One StepTrace per benchmark step. Pure builders — no I/O, no browser, no AI. The schema is
versioned and additive: readers must tolerate unknown future keys and missing optional
sections, so v1 files remain readable by later viewers.

Compatibility rules for future versions:
  • never remove or repurpose a v1 key; only add new optional keys / sections.
  • bump SCHEMA_VERSION only for additive changes; keep the same top-level shape.
  • a field that is unavailable (e.g. backend-internal when TRACE_MODE is off) is `null`
    with a sibling `*_unavailable_reason`, never omitted silently.
"""
from __future__ import annotations

from typing import Any, Optional

SCHEMA_VERSION = "planner_trace_v1"

# reason strings used when a field cannot be captured
REASON_BACKEND_OFF = "backend-internal; set TRACE_MODE=true to capture"


def observation(*, url: str, title: str, dom_snapshot: Optional[str], screenshot_before: Optional[str],
                screenshot_after: Optional[str], visible_text_summary: str,
                interactive_element_count: int, elements_summary: list[dict]) -> dict:
    return {
        "url": url,
        "title": title,
        "dom_snapshot_path": dom_snapshot,
        "screenshot_before_path": screenshot_before,
        "screenshot_after_path": screenshot_after,
        "visible_text_summary": visible_text_summary,
        "interactive_element_count": interactive_element_count,
        "elements_summary": elements_summary,          # [{selector,text,role}] (capped)
    }


def planner_input(*, task: str, page_context_sent: dict, prior_steps_sent: list[dict],
                  compressed_context: Optional[dict], system_prompt_version: Optional[str],
                  model: Optional[str], timestamp: float,
                  strategy_generation_context: Optional[list[dict]] = None) -> dict:
    """What the benchmark transmitted to /analyze (exact), plus backend-internal fields."""
    url = page_context_sent.get("url", "") if isinstance(page_context_sent, dict) else ""
    visible_text = page_context_sent.get("visible_text", "") if isinstance(page_context_sent, dict) else ""
    return {
        "task": task,
        "url": url,
        "observation_summary": (visible_text or "")[:400],
        "page_context_sent": page_context_sent,        # exact payload transmitted
        "prior_steps_sent": prior_steps_sent,          # exact history transmitted
        "strategy_generation_context": strategy_generation_context or [],
        "strategy_generation_context_present": bool(strategy_generation_context),
        "compressed_context": compressed_context,      # backend-internal (null unless TRACE_MODE)
        "compressed_context_unavailable_reason": None if compressed_context is not None else REASON_BACKEND_OFF,
        "system_prompt_version": system_prompt_version,
        "model": model,
        "timestamp": timestamp,
    }


def provider_request(exchange: Optional[dict]) -> dict:
    """From the backend side-channel (TRACE_MODE). None when tracing off/unavailable."""
    if not exchange:
        return {"available": False, "reason": REASON_BACKEND_OFF}
    req = exchange.get("request", {})
    return {
        "available": True,
        "provider": req.get("provider"),
        "model": req.get("model"),
        "system_prompt": req.get("system"),
        "assembled_prompt": req.get("messages"),       # exact system+user messages sent to provider
        "temperature": req.get("temperature"),
        "max_tokens": req.get("max_tokens"),
        "response_format": req.get("response_format"),
        "captured_at": exchange.get("captured_at"),
    }


def provider_response(exchange: Optional[dict], *, parsed: dict, parse_error: Optional[str]) -> dict:
    """Raw provider text (backend) + parsed result (benchmark-visible)."""
    raw = exchange.get("response", {}) if exchange else {}
    return {
        "raw_text": raw.get("raw_text"),               # exact pre-parse text (TRACE_MODE)
        "raw_text_available": bool(exchange),
        "raw_text_unavailable_reason": None if exchange else REASON_BACKEND_OFF,
        "finish_reason": raw.get("finish_reason"),
        "usage": raw.get("usage"),
        "latency_ms": exchange.get("latency_ms") if exchange else None,
        "parsed_json": parsed,                          # analysis + suggested_actions (from /analyze)
        "parse_error": parse_error,
    }


def parsed_action(*, analysis: str, action_type: Optional[str], target: Optional[str],
                  value: Optional[str], reasoning: Optional[str], confidence: Optional[float],
                  clarification: Optional[str]) -> dict:
    return {
        "analysis": analysis,
        "action_type": action_type,
        "target_selector": target,
        "value": value,
        "reasoning": reasoning,
        "confidence": confidence,
        "clarification_question": clarification,
    }


def executor(*, locator_strategy: Optional[str], selector_used: Optional[str], locator_attempts: int,
             start_ms: float, end_ms: float, duration_ms: float, result: str,
             browser_error: Optional[str]) -> dict:
    return {
        "locator_strategy": locator_strategy,
        "selector_used": selector_used,
        "locator_attempts": locator_attempts,
        "execution_start_ms": round(start_ms, 2),
        "execution_end_ms": round(end_ms, 2),
        "execution_duration_ms": round(duration_ms, 2),
        "execution_result": result,                    # "success" | "failed"
        "browser_error": browser_error,
    }


def validation(*, validation_type: str, passed: Optional[bool], reason: str,
               dom_changed: Optional[bool], url_changed: Optional[bool],
               success_criteria_satisfied: bool) -> dict:
    return {
        "validation_type": validation_type,
        "validation_result": passed,
        "validation_reason": reason,
        "dom_changed": dom_changed,
        "url_changed": url_changed,
        "success_criteria_satisfied": success_criteria_satisfied,
    }


def loop_decision(*, decision: str, reason: str) -> dict:
    # decision ∈ {continue, recovered, completed, stuck, failed, timeout, blocked}
    return {"decision": decision, "reason": reason}


def step_trace(*, trace_id: str, run_id: str, task_id: str, session_id: str, step_index: int,
               observation: dict, planner_input: dict, provider_request: dict,
               provider_response: dict, parsed_action: dict, executor: dict,
               validation: dict, loop_decision: dict, metadata: Optional[dict] = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "run_id": run_id,
        "task_id": task_id,
        "session_id": session_id,
        "step_index": step_index,
        "metadata": metadata or {},
        "observation": observation,
        "planner_input": planner_input,
        "provider_request": provider_request,
        "provider_response": provider_response,
        "parsed_action": parsed_action,
        "executor": executor,
        "validation": validation,
        "loop_decision": loop_decision,
    }
