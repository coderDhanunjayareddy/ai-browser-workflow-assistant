"""
M0.6 — Trace viewer (self-contained HTML, no external deps, works offline).

Reads the step_*.trace.json files for one task and renders a single HTML file:
  • left panel   — step list (status-coloured)
  • center       — provider request (exact prompt) · raw response · parsed action · screenshots
  • right panel  — executor · validation · loop decision · metrics · timeline
Clicking a step shows every artifact for that step. Screenshot/DOM paths are rewritten
relative to the viewer file so images load with no server.
"""
from __future__ import annotations

import copy
import html
import json
import os
from typing import Optional

from benchmark.trace import schema


def generate_viewer(*, out_dir: str, run_id: str, task_id: str, artifacts_dir: str) -> Optional[str]:
    task_dir = os.path.join(out_dir, run_id, task_id)
    if not os.path.isdir(task_dir):
        return None
    step_files = sorted(f for f in os.listdir(task_dir) if f.endswith(".trace.json"))
    traces = []
    for sf in step_files:
        with open(os.path.join(task_dir, sf), "r", encoding="utf-8") as f:
            traces.append(json.load(f))
    if not traces:
        return None

    # rewrite artifact paths (relative to artifacts_dir) → relative to the viewer file dir
    view = copy.deepcopy(traces)
    for t in view:
        obs = t.get("observation", {})
        for key in ("dom_snapshot_path", "screenshot_before_path", "screenshot_after_path"):
            p = obs.get(key)
            if p:
                abs_p = os.path.join(artifacts_dir, p)
                obs[key] = os.path.relpath(abs_p, task_dir).replace("\\", "/")

    data_json = json.dumps(view)
    out_path = os.path.join(task_dir, "viewer.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_HTML.replace("__RUN__", html.escape(run_id))
                     .replace("__TASK__", html.escape(task_id))
                     .replace("__SCHEMA__", schema.SCHEMA_VERSION)
                     .replace("/*__DATA__*/", "window.__TRACES__ = " + data_json + ";"))
    return out_path


_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trace — __TASK__ (__RUN__)</title>
<style>
 :root{font-family:-apple-system,Segoe UI,Roboto,sans-serif;}
 *{box-sizing:border-box}
 body{margin:0;background:#0f1115;color:#e6e8eb;font-size:13px}
 header{padding:10px 16px;border-bottom:1px solid #232733;display:flex;gap:16px;align-items:baseline}
 header b{font-size:15px}.muted{color:#9aa0aa}
 #wrap{display:grid;grid-template-columns:210px 1fr 340px;height:calc(100vh - 46px)}
 #steps{border-right:1px solid #232733;overflow:auto}
 .stepbtn{padding:9px 12px;border-bottom:1px solid #1b1f27;cursor:pointer;display:flex;
   justify-content:space-between;gap:8px}
 .stepbtn:hover{background:#161a22}.stepbtn.sel{background:#1c2230}
 .dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto;margin-top:4px}
 .continue{background:#3b82f6}.recovered{background:#e8c454}.completed{background:#56d98a}
 .stuck,.failed,.timeout,.blocked{background:#ff6b6b}
 #center,#right{overflow:auto;padding:14px}
 #right{border-left:1px solid #232733}
 h3{margin:16px 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#9aa0aa}
 pre{background:#0b0e13;border:1px solid #232733;border-radius:6px;padding:10px;white-space:pre-wrap;
   word-break:break-word;max-height:340px;overflow:auto;margin:0}
 .kv{display:grid;grid-template-columns:130px 1fr;gap:2px 10px;margin:2px 0}
 .kv div:first-child{color:#9aa0aa}
 img{max-width:100%;border:1px solid #232733;border-radius:6px;margin-top:6px}
 .imgs{display:grid;grid-template-columns:1fr 1fr;gap:10px}
 .warn{color:#e8c454}.bad{color:#ff8585}.good{color:#56d98a}
 .tl{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}
 .tl span{padding:2px 6px;border-radius:4px;background:#1c2230;cursor:pointer;font-size:11px}
 code{color:#9ecbff}
</style></head><body>
<header><b>Planner Trace</b><span class="muted">task __TASK__ · run __RUN__ · __SCHEMA__</span></header>
<div id="wrap">
 <div id="steps"></div>
 <div id="center"></div>
 <div id="right"></div>
</div>
<script>/*__DATA__*/
const T = window.__TRACES__ || [];
const esc = s => (s==null?"":String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const j = o => esc(JSON.stringify(o,null,2));
function decClass(t){return (t.loop_decision&&t.loop_decision.decision)||'continue';}
function renderSteps(sel){
  document.getElementById('steps').innerHTML = T.map((t,i)=>
    `<div class="stepbtn ${i===sel?'sel':''}" onclick="show(${i})">
       <span>step ${t.step_index}<br><span class="muted">${esc((t.parsed_action&&t.parsed_action.action_type)||'—')}</span></span>
       <span class="dot ${decClass(t)}"></span></div>`).join('');
}
function pReq(t){
  const r=t.provider_request||{};
  if(!r.available) return `<pre class="warn">${esc(r.reason||'unavailable')}</pre>`;
  return `<div class="kv"><div>provider</div><div>${esc(r.provider)} · ${esc(r.model)}</div>
    <div>temperature</div><div>${esc(r.temperature)}</div>
    <div>max_tokens</div><div>${esc(r.max_tokens)}</div></div>
    <h3>Assembled prompt (exact)</h3><pre>${j(r.assembled_prompt)}</pre>`;
}
function pResp(t){
  const r=t.provider_response||{};
  const raw = r.raw_text_available ? `<pre>${esc(r.raw_text)}</pre>`
    : `<pre class="warn">${esc(r.raw_text_unavailable_reason||'unavailable')}</pre>`;
  return `<div class="kv"><div>finish_reason</div><div>${esc(r.finish_reason)}</div>
    <div>usage</div><div>${esc(JSON.stringify(r.usage))}</div>
    <div>latency_ms</div><div>${esc(r.latency_ms)}</div></div>
    <h3>Raw provider response (pre-parse)</h3>${raw}
    <h3>Parsed JSON</h3><pre>${j(r.parsed_json)}</pre>`;
}
function pAct(t){
  const a=t.parsed_action||{};
  return `<div class="kv">
    <div>action_type</div><div><code>${esc(a.action_type)}</code></div>
    <div>target_selector</div><div><code>${esc(a.target_selector)}</code></div>
    <div>value</div><div>${esc(a.value)}</div>
    <div>confidence</div><div>${esc(a.confidence)}</div></div>
    <h3>Reasoning</h3><pre>${esc(a.reasoning||'(none returned)')}</pre>
    <h3>Analysis</h3><pre>${esc(a.analysis||'')}</pre>`;
}
function pObs(t){
  const o=t.observation||{};
  const img=(p,l)=>p?`<div><div class="muted">${l}</div><img src="${esc(p)}"></div>`
                    :`<div><div class="muted">${l}</div><div class="muted">— none —</div></div>`;
  return `<div class="kv"><div>url</div><div><code>${esc(o.url)}</code></div>
    <div>elements</div><div>${esc(o.interactive_element_count)}</div></div>
    <div class="imgs">${img(o.screenshot_before_path,'before')}${img(o.screenshot_after_path,'after')}</div>
    <h3>Visible text (summary)</h3><pre>${esc(o.visible_text_summary)}</pre>
    <h3>Elements the model saw</h3><pre>${j(o.elements_summary)}</pre>`;
}
function pExecVal(t){
  const e=t.executor||{},v=t.validation||{},d=t.loop_decision||{};
  const okc=v.validation_result?'good':(v.validation_result===false?'bad':'');
  return `<h3>Executor</h3><div class="kv">
    <div>locator_strategy</div><div>${esc(e.locator_strategy)}</div>
    <div>selector_used</div><div><code>${esc(e.selector_used)}</code></div>
    <div>attempts</div><div>${esc(e.locator_attempts)}</div>
    <div>duration_ms</div><div>${esc(e.execution_duration_ms)}</div>
    <div>result</div><div class="${e.execution_result==='success'?'good':'bad'}">${esc(e.execution_result)}</div>
    <div>browser_error</div><div class="bad">${esc(e.browser_error)}</div></div>
   <h3>Validation</h3><div class="kv">
    <div>result</div><div class="${okc}">${esc(v.validation_result)}</div>
    <div>dom_changed</div><div>${esc(v.dom_changed)}</div>
    <div>url_changed</div><div>${esc(v.url_changed)}</div>
    <div>criteria_met</div><div>${esc(v.success_criteria_satisfied)}</div>
    <div>reason</div><div>${esc(v.validation_reason)}</div></div>
   <h3>Loop decision</h3><div class="kv">
    <div>decision</div><div class="${decClass(t)==='completed'?'good':(decClass(t)==='continue'||decClass(t)==='recovered'?'warn':'bad')}">${esc(d.decision)}</div>
    <div>reason</div><div>${esc(d.reason)}</div></div>
   <h3>Timeline</h3><div class="tl">${T.map((x,i)=>`<span onclick="show(${i})">${i}·${esc(decClass(x))}</span>`).join('')}</div>`;
}
function show(i){
  renderSteps(i);
  const t=T[i];
  document.getElementById('center').innerHTML =
    `<h3>Observation</h3>${pObs(t)}<h3>Provider request</h3>${pReq(t)}
     <h3>Provider response</h3>${pResp(t)}<h3>Parsed action</h3>${pAct(t)}`;
  document.getElementById('right').innerHTML = pExecVal(t);
}
if(T.length) show(0); else document.getElementById('center').innerHTML='<p class="muted">No trace steps.</p>';
</script></body></html>"""
