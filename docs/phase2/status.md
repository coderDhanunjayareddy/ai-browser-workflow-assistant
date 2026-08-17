# Phase 2 — CDP control and hybrid grounding

Status: **implemented and verified for the current extension path**  
Date: 2026-08-17

## Live execution design

The existing DOM executor remains the fast path. When it returns a verified effect, CDP is never attached. If it fails or produces `no_effect`, the extension may use the CDP fallback only when all of these conditions hold:

1. the user explicitly enabled **Advanced** in the side panel;
2. the loaded extension manifest has Chrome's required `debugger` capability;
3. the action passed the Phase 1 policy gate;
4. the action is marked safe and is not consequential or duplicate-sensitive;
5. the action is one of the supported CDP input classes.

Consequential actions such as submit, send, purchase, payment, delete, publish, transfer, booking, and confirmation are never automatically retried through CDP.

## Permission and lifecycle

- [Chrome explicitly forbids `debugger` in `optional_permissions`](https://developer.chrome.com/docs/extensions/reference/api/permissions#implement), so it is declared in required `permissions` and Chrome presents its warning when the extension is installed or reloaded.
- The user-operated **Advanced** toggle controls runtime use. The extension never attaches through CDP while it is off.
- Disabling Advanced clears the stored runtime preference; required manifest permissions cannot be removed through `chrome.permissions.remove()`.
- Each fallback attaches to only the bound tab, enables the required CDP domains, and detaches in `finally` after success or failure.
- The controller inventories targets and the nested frame tree and listens for bounded navigation/target lifecycle signals during execution.

## Hybrid grounding ladder

1. Existing DOM/widget executors and selector recovery.
2. CDP recursive selector grounding across the main document, open shadow roots, and accessible same-origin frames.
3. CDP Accessibility-tree role/name grounding with backend DOM node box geometry.
4. Screenshot-backed coordinate fallback using the policy-bound observation-time region for visual/canvas/SVG/chart/map actions.

The last step captures a screenshot only locally, stores only its SHA-256 hash in evidence, and never uploads image data. This is a safe coordinate/visual-region fallback, not a claim that an external vision model is identifying arbitrary targets.

## Trusted input

The CDP adapter uses `Input.dispatchMouseEvent`, `Input.dispatchKeyEvent`, and `Input.insertText` for clicks, hover, scroll, controlled input, selection/date input, keyboard shortcuts, and coordinate-oriented visual widgets.

Popup and navigation signals are counted as effect evidence. Page URL stability is still checked around the Phase 1 policy decision.

## Paired adapter traces

For every action, a bounded trace records:

- DOM success and verification reason;
- whether CDP was enabled and attempted;
- CDP success and verification reason;
- grounding source, duration, target/frame counts, and navigation-signal count;
- screenshot hash when the visual-region fallback was used.

The latest 200 traces are retained in extension local storage under `phase2_adapter_traces`. Primitive trace fields also flow into normal browser execution evidence; raw DOM and screenshots are excluded.

## Exit-gate benchmark

Controlled benchmark: [controlled-benchmark-2026-08-17.json](controlled-benchmark-2026-08-17.json)

| Surface | Synthetic DOM effect | Hybrid effect |
|---|---:|---:|
| Controlled input requiring trusted events | No | Yes |
| Nested iframe control | No | Yes |
| Popup requiring trusted click | No | Yes |
| Canvas-style complex widget | No | Yes |

- Synthetic no-effect rate: **100% (4/4)**
- Hybrid no-effect rate: **0% (0/4)**
- Relative no-effect reduction: **100% on the controlled suite**

This satisfies the stated controlled-suite exit gate. It does not claim that every cross-origin iframe or arbitrary visual target on the public web is solved.

## Verification evidence

- Extension tests: **151 passed**
- Backend benchmark/policy/governance tests: **188 passed**
- Phase 2 CDP and manifest-permission tests: **8 passed** (included in extension total)
- TypeScript: `tsc --noEmit` passed
- Production extension: `vite build` passed
- Controlled trusted-input benchmark: **4/4 hybrid effects verified**

Commands:

```text
cd extension && node --test --test-concurrency=1 tests/*.test.cjs
cd extension && npm run type-check
cd extension && npm run build
cd backend && .venv-codex/Scripts/python.exe -m pytest tests/benchmark tests/unit/test_phase1_live_policy.py tests/unit/test_phase1_policy_api.py tests/unit/test_phase1_prompt_injection.py tests/unit/test_v3_governance.py -q
cd backend && .venv-codex/Scripts/python.exe -m benchmark.phase2_control_benchmark --output ../docs/phase2/controlled-benchmark-2026-08-17.json
```

## Activation

Remove or reload the old unpacked extension, then load `extension/dist` and verify version **0.2.1** on `chrome://extensions`. Chrome will show the debugger warning during load/reload. Open the Workflow panel and switch **Advanced** on. Leaving Advanced off preserves the old DOM-only behavior and never attaches CDP.
