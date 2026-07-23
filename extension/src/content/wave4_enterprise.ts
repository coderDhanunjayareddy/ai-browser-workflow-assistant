export interface Wave4Action {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
  reasoning?: string
  safety_level?: string
}

export interface Wave4Result {
  success: boolean
  message: string
  action_id: string
  wave4_capability?: string
  wave4_validated?: boolean
  wave4_details?: Record<string, string | number | boolean | null>
}

const WAVE4_ACTIONS = new Set([
  'google_workspace_adapter',
  'microsoft365_adapter',
  'github_advanced_adapter',
  'jira_adapter',
  'confluence_adapter',
  'slack_adapter',
  'notion_adapter',
  'figma_adapter',
  'canva_adapter',
  'salesforce_adapter',
  'sso_auth',
  'mfa_otp_handoff',
  'enterprise_file_workflow',
  'site_optimize',
])

export function parseWave4Payload(value: string | null): Record<string, unknown> {
  if (!value) return {}
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : { text: value }
  } catch {
    return { text: value }
  }
}

export function isWave4EnterpriseAction(actionType: string): boolean {
  return WAVE4_ACTIONS.has(actionType)
}

export async function executeWave4EnterpriseAction(action: Wave4Action): Promise<Wave4Result | null> {
  const wave4Actions = new Set([
    'google_workspace_adapter',
    'microsoft365_adapter',
    'github_advanced_adapter',
    'jira_adapter',
    'confluence_adapter',
    'slack_adapter',
    'notion_adapter',
    'figma_adapter',
    'canva_adapter',
    'salesforce_adapter',
    'sso_auth',
    'mfa_otp_handoff',
    'enterprise_file_workflow',
    'site_optimize',
  ])
  if (!wave4Actions.has(action.action_type)) return null
  if (action.safety_level === 'danger') {
    return { success: false, message: 'Wave 4 action refused because it is marked dangerous.', action_id: action.action_id }
  }

  const payload = (() => {
    if (!action.value) return {}
    try {
      const parsed = JSON.parse(action.value)
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : { text: action.value }
    } catch {
      return { text: action.value }
    }
  })()

  const profiles: Record<string, {
    capability: string
    selectors: string[]
    workflows: string[]
    optimizations: string[]
  }> = {
    google_workspace_adapter: { capability: 'browser.adapters.google_workspace', selectors: ['[role="textbox"]', '[aria-label*="Search"]', '[aria-label*="Compose"]', '[data-tooltip]'], workflows: ['docs_edit', 'sheets_navigation', 'drive_preview', 'gmail_compose'], optimizations: ['rich_text', 'large_tables', 'preview_dialogs'] },
    microsoft365_adapter: { capability: 'browser.adapters.microsoft365', selectors: ['[role="textbox"]', '[aria-label*="Search"]', '[data-automationid]', '.ms-Button'], workflows: ['word_edit', 'excel_grid_navigation', 'outlook_compose'], optimizations: ['rich_text', 'large_tables', 'enterprise_dashboards'] },
    github_advanced_adapter: { capability: 'browser.adapters.github_advanced', selectors: ['[data-testid]', '[aria-label]', '.cm-editor', '.monaco-editor'], workflows: ['pull_request_review', 'code_search', 'web_editor'], optimizations: ['code_editors', 'keyboard_navigation'] },
    jira_adapter: { capability: 'browser.adapters.jira', selectors: ['[data-testid]', '[aria-label]', '[role="dialog"]', '[contenteditable="true"]'], workflows: ['issue_search', 'issue_update', 'board_move'], optimizations: ['virtualized_ui', 'rich_text', 'drag_drop'] },
    confluence_adapter: { capability: 'browser.adapters.confluence', selectors: ['[data-testid]', '[contenteditable="true"]', '[aria-label]', '[role="dialog"]'], workflows: ['page_edit', 'comment', 'search'], optimizations: ['rich_text', 'file_preview'] },
    slack_adapter: { capability: 'browser.adapters.slack', selectors: ['[data-qa]', '[role="textbox"]', '[aria-label]', '.ql-editor'], workflows: ['message_compose', 'channel_search', 'thread_reply'], optimizations: ['rich_text', 'virtualized_ui'] },
    notion_adapter: { capability: 'browser.adapters.notion', selectors: ['[contenteditable="true"]', '[data-block-id]', '[role="button"]', '[aria-label]'], workflows: ['page_edit', 'database_update', 'search'], optimizations: ['rich_text', 'virtualized_ui'] },
    figma_adapter: { capability: 'browser.adapters.figma', selectors: ['canvas', '[data-testid]', '[aria-label]', '[role="button"]'], workflows: ['canvas_select', 'comment', 'file_navigation'], optimizations: ['canvas', 'visual_regions'] },
    canva_adapter: { capability: 'browser.adapters.canva', selectors: ['canvas', '[data-testid]', '[aria-label]', '[role="button"]'], workflows: ['design_edit', 'asset_preview', 'export_dialog'], optimizations: ['canvas', 'file_preview'] },
    salesforce_adapter: { capability: 'browser.adapters.salesforce', selectors: ['[data-aura-class]', '[data-target-selection-name]', '[aria-label]', '[role="button"]'], workflows: ['record_search', 'record_update', 'dashboard_navigation'], optimizations: ['enterprise_dashboards', 'large_tables'] },
  }

  function countSelectors(selectors: string[]): { total: number, counts: Record<string, number> } {
    const counts: Record<string, number> = {}
    let total = 0
    for (const selector of selectors) {
      try {
        const count = document.querySelectorAll(selector).length
        counts[selector] = count
        total += count
      } catch {
        counts[selector] = -1
      }
    }
    return { total, counts }
  }

  function adapterResult(): Wave4Result | null {
    const profile = profiles[action.action_type]
    if (!profile) return null
    const counted = countSelectors(profile.selectors)
    return {
      success: true,
      message: `${profile.capability} metadata collected.`,
      action_id: action.action_id,
      wave4_capability: profile.capability,
      wave4_validated: true,
      wave4_details: {
        discovered_elements: counted.total,
        workflow_count: profile.workflows.length,
        optimization_count: profile.optimizations.length,
        dialog_count: document.querySelectorAll('[role="dialog"], dialog, [aria-modal="true"]').length,
      },
    }
  }

  function authResult(kind: 'sso' | 'mfa'): Wave4Result {
    const text = (document.body?.innerText || '').replace(/\s+/g, ' ').trim()
    const inputs = Array.from(document.querySelectorAll('input'))
    const sso = /single sign|\bsso\b|oauth|authorize|continue with google|continue with microsoft|company account|organization/i.test(text)
    const mfa = /multi-factor|two-factor|authenticator|verification code|security code|one-time|otp|enter code/i.test(text) ||
      inputs.some((input) => /one-time-code|otp/i.test(`${input.getAttribute('autocomplete') || ''} ${input.getAttribute('name') || ''} ${input.getAttribute('aria-label') || ''}`))
    const captcha = /captcha|recaptcha|hcaptcha/i.test(text)
    const capability = kind === 'sso' ? 'browser.auth.enterprise_sso' : 'browser.auth.mfa_otp_handoff'
    const valid = kind === 'sso' ? sso : mfa
    return { success: valid, message: valid ? `${kind} handoff metadata detected.` : `${kind} handoff metadata not detected.`, action_id: action.action_id, wave4_capability: capability, wave4_validated: valid, wave4_details: { sso_detected: sso, mfa_detected: mfa, captcha_detected: captcha, password_field_count: inputs.filter((input) => input.type === 'password').length } }
  }

  function fileWorkflow(): Wave4Result {
    const count = document.querySelectorAll('input[type=file], [aria-label*="Upload" i], [aria-label*="Download" i], [data-testid*="upload" i], [data-testid*="download" i], a[download], [role="dialog"]').length
    return { success: count > 0 || String(payload.workflow ?? 'detect') === 'detect', message: 'Enterprise file workflow metadata collected.', action_id: action.action_id, wave4_capability: 'browser.enterprise_file_workflows', wave4_validated: true, wave4_details: { candidate_count: count, workflow: String(payload.workflow ?? 'detect') } }
  }

  function optimize(): Wave4Result {
    const rich = document.querySelectorAll('[contenteditable=true], [contenteditable="true"]').length
    const tables = document.querySelectorAll('table, [role=grid], [role=table]').length
    const virtual = document.querySelectorAll('[style*="transform: translate"], [data-virtualized], [aria-rowcount]').length
    const visual = document.querySelectorAll('canvas, svg, [class*=chart], [class*=dashboard]').length
    return { success: true, message: 'Site optimization metadata collected.', action_id: action.action_id, wave4_capability: 'browser.site_optimization.framework', wave4_validated: true, wave4_details: { rich_text_surfaces: rich, table_surfaces: tables, virtual_signals: virtual, visual_surfaces: visual } }
  }

  if (profiles[action.action_type]) return adapterResult()
  if (action.action_type === 'sso_auth') return authResult('sso')
  if (action.action_type === 'mfa_otp_handoff') return authResult('mfa')
  if (action.action_type === 'enterprise_file_workflow') return fileWorkflow()
  if (action.action_type === 'site_optimize') return optimize()
  return null
}
