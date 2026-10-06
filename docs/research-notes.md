# Research notes for Version 1

Research informs the general workflow; no paper is copied wholesale. The owner wants complete web tasks, with travel booking as a diagnostic case rather than hardcoded logic.

| Source | Useful insight | Decision |
|---|---|---|
| [ReAct](https://arxiv.org/abs/2210.03629) | Re-read after each action. | Adopt now: one bounded observe/act/check loop. |
| [WebArena](https://arxiv.org/abs/2307.13854) and [WorkArena](https://arxiv.org/abs/2403.07718) | Grade the final user outcome on realistic sites. | Adopt now: real side-panel end-to-end evidence. |
| [Mind2Web](https://arxiv.org/abs/2306.06070) | Raw page HTML is too large. | Adopt now: compact relevant controls and text. |
| [WebVoyager](https://arxiv.org/abs/2401.13919) | Images can help where page structure fails. | Later: bounded visual fallback, not screenshot-first control. |
| [ST-WebAgentBench](https://arxiv.org/abs/2410.06703) | Completion without policy compliance is unsafe. | Adopt now: measure both success and safety violations. |
| [BrowserArena](https://arxiv.org/abs/2510.02418) | Live popups, CAPTCHA, and navigation cause distinct failures. | Adopt now: first-failure categories and honest stops. |
| [Beyond Browsing](https://arxiv.org/abs/2410.16464) | Official APIs may avoid fragile clicks. | Later: use only when a selected service offers an authorized API. |
| [GUI-agent survey](https://arxiv.org/abs/2411.18279) and [agent-evaluation survey](https://arxiv.org/abs/2503.16416) | Perception, planning, action, safety, cost, and evaluation must connect. | Adopt now: explicit module ownership and whole-task metrics. |
| [OSWorld](https://arxiv.org/abs/2404.07972) | Verify real end states in complex environments. | Adopt the testing lesson; desktop automation is outside this Chrome extension. |
| [Chrome permissions](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab), [worker lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle), and [debugger](https://developer.chrome.com/docs/extensions/reference/api/debugger) | Permissions, tab access, and short-lived workers shape the design. | Adopt now: least practical access, durable state, explicit privileged dispatch. |

Rejected for initial Version 1: a universal autonomous agent, a screenshot-first executor, silent payment or booking commitment, long-term personal memory, and a second independent browser executor. These add risk before the current path is proven.

