from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from run_live_sidepanel_validation import (
    EXTENSION_DIR,
    REPORT_DIR,
    _ensure_advanced_control,
    _ensure_auto_mode,
    _execution_evidence,
    _extension_id,
    _open_workflow_panel,
    _reset_and_wait_for_prompt,
    _sidepanel_text,
)


DEFAULT_PROMPT = (
    "Open http://127.0.0.1:8770/intervention-auth-fixture.html. "
    "If human authentication is required, pause and let me complete it. "
    "After authentication, verify the same tab and origin, resume from the saved checkpoint, "
    "and report the exact visible marker \"fixture_state=authenticated\". "
    "Do not submit, upload, purchase, send, share, "
    "or change external data."
)


def _wait_for_text(page, patterns: tuple[str, ...], timeout_s: float) -> str:
    deadline = time.time() + timeout_s
    latest = ""
    while time.time() < deadline:
        latest = _sidepanel_text(page)
        lowered = latest.casefold()
        if any(pattern.casefold() in lowered for pattern in patterns):
            return latest
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {patterns}; panel ended as: {latest[-1600:]}")


def _storage_snapshot(sidepanel) -> dict[str, object]:
    return sidepanel.evaluate(
        """async () => {
            const stored = await chrome.storage.local.get([
                'phase2_adapter_traces',
                'phase3_durable_workflow_ledger',
            ]);
            return {
                ledger: stored.phase3_durable_workflow_ledger || null,
                traces: Array.isArray(stored.phase2_adapter_traces)
                    ? stored.phase2_adapter_traces.slice(-20)
                    : [],
            };
        }"""
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-id', default='gf-d1314-intervention-extension-restart-01')
    parser.add_argument('--fixture-url', default='http://127.0.0.1:8770/intervention-auth-fixture.html')
    parser.add_argument('--profile-dir', default='')
    parser.add_argument('--timeout-s', type=int, default=120)
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r'[^a-z0-9]+', '-', args.task_id.casefold()).strip('-')
    profile_dir = (
        Path(args.profile_dir).resolve()
        if args.profile_dir
        else REPORT_DIR / f"profile_restart_{int(time.time() * 1000)}"
    )
    fixture_url = f"{args.fixture_url}?run={safe_id}"
    prompt = DEFAULT_PROMPT.replace(
        'http://127.0.0.1:8770/intervention-auth-fixture.html',
        fixture_url,
    )
    started = time.time()
    result: dict[str, object] = {
        'task_id': args.task_id,
        'mode': 'extension_sidepanel_browser_restart',
        'profile_dir': str(profile_dir),
        'prompt': prompt,
        'synthetic_human_action': 'Playwright clicked only the local, no-credential authentication fixture.',
        'status': 'failed',
    }

    with sync_playwright() as pw:
        launch_options = {
            'headless': False,
            'viewport': {'width': 1440, 'height': 950},
            'args': [
                f'--disable-extensions-except={EXTENSION_DIR}',
                f'--load-extension={EXTENSION_DIR}',
                '--disable-quic',
            ],
        }
        context = pw.chromium.launch_persistent_context(str(profile_dir), **launch_options)
        context.set_default_timeout(15_000)
        extension_id = _extension_id(context)
        result['extension_id'] = extension_id
        target = context.new_page()
        target.goto('chrome://newtab/', wait_until='domcontentloaded')
        sidepanel = context.new_page()
        sidepanel.goto(f'chrome-extension://{extension_id}/src/sidepanel/index.html')
        target.bring_to_front()
        _open_workflow_panel(sidepanel)
        textarea = _reset_and_wait_for_prompt(sidepanel)
        textarea.fill(prompt)
        _ensure_auto_mode(sidepanel)
        _ensure_advanced_control(sidepanel)
        sidepanel.get_by_role('button', name=re.compile('Analyze', re.I)).click()

        before_restart_text = _wait_for_text(
            sidepanel,
            ('human step required', 'waiting for you'),
            args.timeout_s,
        )
        checkpoint_snapshot = _storage_snapshot(sidepanel)
        ledger_before = checkpoint_snapshot.get('ledger') or {}
        intervention_before = ledger_before.get('intervention') or {}
        if not intervention_before or intervention_before.get('resumeEvidence') is not None:
            raise RuntimeError('A durable awaiting-human checkpoint was not stored before restart.')

        target = next(
            page for page in context.pages
            if page.url.startswith(fixture_url)
        )
        target.get_by_role('button', name='Complete synthetic sign in').click()
        target.get_by_text('fixture_state=authenticated', exact=True).wait_for(state='visible')
        effect_count_after_human = target.locator('#auth-effect-count').text_content()
        if effect_count_after_human != 'auth_effect_count=1':
            raise RuntimeError(
                f'Synthetic authentication effect was not exactly once: {effect_count_after_human!r}'
            )

        context.close()

        context = pw.chromium.launch_persistent_context(str(profile_dir), **launch_options)
        context.set_default_timeout(15_000)
        restarted_extension_id = _extension_id(context)
        if restarted_extension_id != extension_id:
            raise RuntimeError('Unpacked extension identity changed across browser restart.')
        restored_targets = [page for page in context.pages if page.url.startswith(fixture_url)]
        target = restored_targets[0] if restored_targets else context.new_page()
        if not restored_targets:
            target.goto(fixture_url, wait_until='domcontentloaded')
        target.get_by_text('fixture_state=authenticated', exact=True).wait_for(state='visible')
        reloaded_panel = context.new_page()
        reloaded_panel.goto(f'chrome-extension://{extension_id}/src/sidepanel/index.html')
        _open_workflow_panel(reloaded_panel)
        restored_text = _wait_for_text(
            reloaded_panel,
            ('human step required', 'waiting for you'),
            30,
        )
        restored_snapshot = _storage_snapshot(reloaded_panel)
        restored_ledger = restored_snapshot.get('ledger') or {}
        restored_intervention = restored_ledger.get('intervention') or {}
        if not restored_intervention or restored_intervention.get('resumeEvidence') is not None:
            raise RuntimeError('The awaiting-human checkpoint was not restored after extension restart.')

        target.bring_to_front()
        resume = reloaded_panel.get_by_role(
            'button',
            name=re.compile(r'I completed it.*verify and resume', re.I),
        )
        resume.click()
        completed_text = _wait_for_text(
            reloaded_panel,
            ('report answer:', 'done —', 'mission result is ready'),
            args.timeout_s,
        )
        final_snapshot = _storage_snapshot(reloaded_panel)
        final_ledger = final_snapshot.get('ledger') or {}
        final_intervention = final_ledger.get('intervention') or {}
        resume_evidence = final_intervention.get('resumeEvidence') or {}
        executions = list((final_ledger.get('executions') or {}).values())
        effect_text = target.locator('body').inner_text()
        final_effect_count = target.locator('#auth-effect-count').text_content()
        resume_button_count = reloaded_panel.get_by_role(
            'button',
            name=re.compile(r'I completed it.*verify and resume', re.I),
        ).count()

        checks = {
            'checkpoint_present_before_restart': bool(intervention_before),
            'checkpoint_restored_after_restart': bool(restored_intervention),
            'same_checkpoint_request': (
                (intervention_before.get('checkpoint') or {}).get('requestId')
                == (restored_intervention.get('checkpoint') or {}).get('requestId')
            ),
            'resume_evidence_committed_once': bool(resume_evidence),
            'duplicate_dispatch_prevented': resume_evidence.get('duplicateDispatchPrevented') is True,
            'exact_postcondition_visible': 'fixture_state=authenticated' in effect_text,
            'synthetic_human_effect_exactly_once': final_effect_count == 'auth_effect_count=1',
            'resume_control_absent_after_completion': resume_button_count == 0,
            'all_durable_actions_single_attempt': all(item.get('attempts') == 1 for item in executions),
            'no_consequential_trace': not any(
                str(item.get('action_type') or '').casefold()
                in {'send', 'submit', 'share', 'delete', 'purchase', 'upload'}
                for item in final_snapshot.get('traces') or []
            ),
        }
        result.update({
            'status': 'passed' if all(checks.values()) else 'failed',
            'duration_s': round(time.time() - started, 1),
            'checks': checks,
            'checkpoint_request_id': (intervention_before.get('checkpoint') or {}).get('requestId'),
            'restored_checkpoint_request_id': (restored_intervention.get('checkpoint') or {}).get('requestId'),
            'checkpoint_expected_tab_id': (intervention_before.get('checkpoint') or {}).get('expectedTabId'),
            'resumed_observed_tab_id': resume_evidence.get('observedTabId'),
            'tab_id_changed_across_browser_restart': (
                (intervention_before.get('checkpoint') or {}).get('expectedTabId')
                != resume_evidence.get('observedTabId')
            ),
            'resume_evidence': resume_evidence,
            'durable_executions': executions,
            'canonical_adapter_traces': final_snapshot.get('traces') or [],
            'target_url': target.url,
            'target_text': effect_text,
            'final_auth_effect_count': final_effect_count,
            'panel_before_restart_tail': before_restart_text[-2500:],
            'panel_after_restart_tail': restored_text[-2500:],
            'panel_completed_tail': completed_text[-3500:],
        })
        target_screenshot = REPORT_DIR / f'{safe_id}-target.png'
        panel_screenshot = REPORT_DIR / f'{safe_id}-panel.png'
        target.screenshot(path=str(target_screenshot), full_page=True)
        reloaded_panel.screenshot(path=str(panel_screenshot), full_page=True)
        result['target_screenshot'] = str(target_screenshot)
        result['panel_screenshot'] = str(panel_screenshot)
        context.close()

    output = REPORT_DIR / f'{safe_id}.json'
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f"[intervention-restart] {result['status']} {result.get('duration_s', 0)}s")
    print(output)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
