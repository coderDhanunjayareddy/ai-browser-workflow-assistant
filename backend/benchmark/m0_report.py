"""
M0 — Report generation (JSON / Markdown / HTML).

JSON is the canonical artifact; Markdown and HTML are derived from the same report dict.
The HTML is fully self-contained — inline <style> + inline <script>, no external assets —
so it can be opened offline or shared as a single file. Screenshots are referenced by
relative path (the report sits alongside the artifacts directory).
"""
from __future__ import annotations

import html
import json
from typing import Any, Optional

from benchmark.m0_models import M0TaskResult
from benchmark import m0_metrics


def build_report(*, meta: dict, results: list[M0TaskResult], executor_mode: str,
                 baseline: Optional[dict] = None) -> dict[str, Any]:
    agg = m0_metrics.aggregate(results, executor_mode=executor_mode)
    summary = dict(agg["summary"])

    if baseline is not None:
        base_rate = baseline.get("summary", {}).get("completion_rate")
        if base_rate is not None:
            summary["completion_rate_delta_from_baseline"] = round(
                summary["completion_rate"] - base_rate, 4)
        summary["baseline_run_id"] = baseline.get("meta", {}).get("run_id")

    recommendations = _recommendations(agg, results)

    return {
        "meta": meta,
        "summary": summary,
        "secondary": agg["secondary"],
        "by_difficulty": agg["by_difficulty"],
        "by_category": agg["by_category"],
        "by_site": agg["by_site"],
        "failure_distribution": agg["failure_distribution"],
        "locator_strategies": agg["locator_strategies"],
        "recommendations": recommendations,
        "task_results": [r.to_dict() for r in results],
    }


def _recommendations(agg: dict, results: list[M0TaskResult]) -> list[str]:
    recs: list[str] = []
    fd = agg["failure_distribution"]
    total_fail = sum(fd.values()) or 1
    ranked = sorted(fd.items(), key=lambda kv: kv[1], reverse=True)
    if ranked:
        top, cnt = ranked[0]
        recs.append(f"Largest failure category: {top} ({cnt}/{total_fail} = {cnt/total_fail:.0%}).")
        if top == "EXECUTION":
            recs.append("EXECUTION dominates — M1 (CDP trusted driver) is the highest-leverage fix.")
        elif top == "GROUNDING":
            recs.append("GROUNDING dominates — wiring locator_engine.LocatorRanker is the priority.")
        elif top == "VISION_REQUIRED":
            recs.append("VISION_REQUIRED dominates — M3 (visual grounding) is needed for these tasks.")
    rec_rate = agg["summary"]["recovery_success_rate"]
    if rec_rate == 0.0:
        recs.append("Recovery success rate is 0% — M2 (closed loop with recovery) is unblocked.")
    gap_present = agg["summary"].get("captcha_blocked_rate", 0)
    if gap_present:
        recs.append(f"{gap_present:.0%} of tasks blocked by CAPTCHA — site defenses, not agent failures.")
    return recs


# ── Markdown ─────────────────────────────────────────────────────────────────

def render_markdown(report: dict) -> str:
    m, s = report["meta"], report["summary"]
    L: list[str] = []
    L.append(f"# M0 Benchmark Report — {m.get('run_id','?')}\n")
    L.append(f"**Suite:** {m.get('suite','?')} | **Executor:** {m.get('executor_mode','?')} | "
             f"**Duration:** {m.get('duration_s',0)}s\n")
    delta = s.get("completion_rate_delta_from_baseline")
    delta_str = f" (Δ {delta:+.1%} vs baseline)" if delta is not None else ""
    L.append("## Summary\n")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Task Completion Rate | **{s['completion_rate']:.1%}**{delta_str} |")
    ci = s.get("completion_rate_ci_95", [0, 0])
    L.append(f"| 95% CI | [{ci[0]:.1%}, {ci[1]:.1%}] |")
    for tier in ("simple", "medium", "complex"):
        b = report["by_difficulty"][tier]
        L.append(f"| {tier.title()} tier | {b['completion_rate']:.1%} "
                 f"({b['completed']}/{b['attempted']}) |")
    L.append(f"| Step Success Rate | {s['step_success_rate']:.1%} |")
    L.append(f"| Human Intervention Rate | {s['human_intervention_rate']:.1%} |")
    L.append(f"| Recovery Success Rate | {s['recovery_success_rate']:.1%} |")
    L.append(f"| Validation Pass Rate | {s['validation_pass_rate']:.1%} |")
    L.append(f"| Estimated Cost | ${s['estimated_cost_usd']:.2f} |")
    L.append("")

    def section(title, statuses):
        rows = [r for r in report["task_results"] if r["status"] in statuses]
        if not rows:
            return
        L.append(f"## {title}")
        for r in rows:
            extra = ""
            if r["failure_layer"]:
                extra = f" — {r['failure_layer']}: {r['failure_detail']}"
            ef = " [expected-failure]" if r["expect_failure"] else ""
            L.append(f"- [{r['status']}] {r['website']}: {r['task_id']} "
                     f"({r['difficulty']}/{r['category']}, {r['steps_taken']} steps){extra}{ef}")
        L.append("")

    section("Completed", {"COMPLETED"})
    section("Failed", {"FAILED", "TIMEOUT", "STUCK", "ERROR"})
    section("Blocked / Skipped", {"BLOCKED", "SKIPPED"})

    if report["failure_distribution"]:
        L.append("## Failure Distribution")
        L.append("| Category | Count |")
        L.append("|---|---|")
        for k, v in sorted(report["failure_distribution"].items(), key=lambda kv: -kv[1]):
            L.append(f"| {k} | {v} |")
        L.append("")

    if report["locator_strategies"]:
        L.append("## Locator Strategy Success")
        L.append("| Strategy | Resolutions |")
        L.append("|---|---|")
        for k, v in sorted(report["locator_strategies"].items(), key=lambda kv: -kv[1]):
            L.append(f"| {k} | {v} |")
        L.append("")

    L.append("## Recommendations")
    for r in report["recommendations"]:
        L.append(f"- {r}")
    return "\n".join(L)


# ── HTML (self-contained) ─────────────────────────────────────────────────────

def render_html(report: dict) -> str:
    m, s = report["meta"], report["summary"]
    rate = s["completion_rate"]
    color = "#c0392b" if rate < 0.40 else ("#d68910" if rate < 0.70 else "#1e8449")
    data_json = json.dumps(report)

    cards = _metric_cards(s)
    tier_rows = "".join(
        f"<tr><td>{t}</td><td>{report['by_difficulty'][t]['completion_rate']:.0%}</td>"
        f"<td>{report['by_difficulty'][t]['completed']}/{report['by_difficulty'][t]['attempted']}</td>"
        f"<td><div class='bar'><div class='fill' style='width:"
        f"{report['by_difficulty'][t]['completion_rate']*100:.0f}%'></div></div></td></tr>"
        for t in ("simple", "medium", "complex"))
    fail_rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>"
                        for k, v in sorted(report["failure_distribution"].items(), key=lambda kv: -kv[1]))
    loc_rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>"
                       for k, v in sorted(report["locator_strategies"].items(), key=lambda kv: -kv[1]))
    task_rows = "".join(_task_row(r) for r in report["task_results"])
    recs = "".join(f"<li>{html.escape(r)}</li>" for r in report["recommendations"])

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>M0 Benchmark — {html.escape(str(m.get('run_id','')))}</title>
<style>
 :root {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; }}
 body {{ margin:0; background:#0f1115; color:#e6e8eb; }}
 header {{ padding:24px 32px; border-bottom:1px solid #232733; display:flex;
          align-items:center; justify-content:space-between; flex-wrap:wrap; gap:16px; }}
 header .meta {{ color:#9aa0aa; font-size:13px; }}
 .big {{ font-size:54px; font-weight:700; color:{color}; line-height:1; }}
 main {{ padding:24px 32px; max-width:1200px; }}
 .cards {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:28px; }}
 .card {{ background:#161a22; border:1px solid #232733; border-radius:10px; padding:16px 20px; min-width:160px; }}
 .card .label {{ color:#9aa0aa; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
 .card .value {{ font-size:26px; font-weight:600; margin-top:6px; }}
 h2 {{ margin-top:32px; font-size:18px; border-bottom:1px solid #232733; padding-bottom:8px; }}
 table {{ width:100%; border-collapse:collapse; font-size:14px; }}
 th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid #1d2129; }}
 th {{ color:#9aa0aa; font-weight:600; }}
 .bar {{ background:#232733; border-radius:6px; height:10px; width:160px; }}
 .fill {{ background:#3b82f6; height:10px; border-radius:6px; }}
 .pill {{ padding:2px 8px; border-radius:10px; font-size:12px; font-weight:600; }}
 .COMPLETED {{ background:#143d28; color:#56d98a; }}
 .FAILED, .TIMEOUT, .STUCK, .ERROR {{ background:#3d1414; color:#ff8585; }}
 .BLOCKED, .SKIPPED {{ background:#3d3414; color:#e8c454; }}
 .task {{ cursor:pointer; }}
 .detail {{ display:none; background:#10131a; }}
 .detail td {{ font-size:13px; color:#aeb4be; }}
 .ef {{ color:#e8c454; font-size:11px; }}
 ul {{ line-height:1.7; }}
 code {{ color:#9ecbff; }}
</style></head><body>
<header>
 <div><div style="font-size:13px;color:#9aa0aa;">M0 REAL WEBSITE BENCHMARK</div>
   <div style="font-size:22px;font-weight:700;">{html.escape(str(m.get('run_id','')))}</div>
   <div class="meta">suite={html.escape(str(m.get('suite','')))} ·
     executor={html.escape(str(m.get('executor_mode','')))} ·
     {html.escape(str(m.get('started_at','')))} · {m.get('duration_s',0)}s</div></div>
 <div style="text-align:right;"><div class="big">{rate:.0%}</div>
   <div class="meta">task completion</div></div>
</header>
<main>
 <div class="cards">{cards}</div>
 <h2>Completion by difficulty</h2>
 <table><tr><th>Tier</th><th>Rate</th><th>Completed</th><th></th></tr>{tier_rows}</table>
 <h2>Failure distribution</h2>
 <table><tr><th>Category</th><th>Count</th></tr>{fail_rows or '<tr><td colspan=2>none</td></tr>'}</table>
 <h2>Locator strategy success</h2>
 <table><tr><th>Strategy</th><th>Resolutions</th></tr>{loc_rows or '<tr><td colspan=2>none</td></tr>'}</table>
 <h2>Tasks</h2>
 <table><tr><th>Status</th><th>Task</th><th>Site</th><th>Tier</th><th>Steps</th><th>Cost·tok</th><th>Failure</th></tr>
 {task_rows}</table>
 <h2>Recommendations</h2><ul>{recs}</ul>
</main>
<script>
 // expandable task rows
 document.querySelectorAll('.task').forEach(function(row){{
   row.addEventListener('click', function(){{
     var d = row.nextElementSibling;
     if (d && d.classList.contains('detail'))
       d.style.display = d.style.display === 'table-row' ? 'none' : 'table-row';
   }});
 }});
 window.__M0_REPORT__ = {data_json};
</script>
</body></html>"""


def _metric_cards(s: dict) -> str:
    items = [
        ("Step success", f"{s['step_success_rate']:.0%}"),
        ("Recovery success", f"{s['recovery_success_rate']:.0%}"),
        ("Validation pass", f"{s['validation_pass_rate']:.0%}"),
        ("Human interventions", f"{s['human_intervention_rate']:.0%}"),
        ("Cost", f"${s['estimated_cost_usd']:.2f}"),
    ]
    return "".join(f"<div class='card'><div class='label'>{html.escape(l)}</div>"
                   f"<div class='value'>{html.escape(v)}</div></div>" for l, v in items)


def _task_row(r: dict) -> str:
    st = html.escape(r["status"])
    ef = "<span class='ef'>⚑ expected-failure</span>" if r["expect_failure"] else ""
    crit = "".join(
        f"<div>{'✓' if c['passed'] else '✗'} {html.escape(c['kind'])}: {html.escape(c['observed'])}</div>"
        for c in r["criteria_results"])
    shots = "".join(f"<div><code>{html.escape(p)}</code></div>" for p in r["screenshots"][:6])
    fail = html.escape(f"{r['failure_layer']}: {r['failure_detail']}" if r["failure_layer"] else "")
    return (
        f"<tr class='task'><td><span class='pill {st}'>{st}</span></td>"
        f"<td>{html.escape(r['task_id'])} {ef}</td><td>{html.escape(r['website'])}</td>"
        f"<td>{html.escape(r['difficulty'])}</td><td>{r['steps_taken']}</td>"
        f"<td>{r['total_tokens']}t</td><td>{fail}</td></tr>"
        f"<tr class='detail'><td colspan='7'><b>goal status:</b>{crit or ' n/a'}"
        f"<br><b>final url:</b> <code>{html.escape(r['final_url'])}</code>"
        f"<br><b>screenshots:</b>{shots or ' none'}</td></tr>")
