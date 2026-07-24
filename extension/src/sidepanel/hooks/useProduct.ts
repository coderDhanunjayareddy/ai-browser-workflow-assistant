import { useCallback, useEffect, useMemo, useState } from 'react'

const BACKEND_URL = 'http://localhost:8000'
const TOKEN_KEY = 'v5_product_token'

export interface ProductUser {
  id: string
  email: string
  name: string
  status: string
  preferences: Record<string, unknown>
}

export interface ProductOrg {
  id: string
  name: string
  slug: string
  role?: string | null
}

export interface ProductWorkspace {
  id: string
  org_id: string
  name: string
  description: string
  role?: string | null
  status: string
  created_at: string
}

export interface ProductWorkflow {
  id: string
  workspace_id: string
  org_id: string
  title: string
  status: string
  input_summary: string
  output_summary: string
  parameters: Record<string, unknown>
  created_at: string
  steps: Array<Record<string, unknown>>
}

export interface ProductReplay {
  workflow: Record<string, unknown>
  timeline: Array<Record<string, unknown>>
  metadata: Record<string, unknown>
}

export interface ProductTask {
  id: string
  workspace_id?: string | null
  scope: string
  title: string
  description: string
  input_prompt: string
  tags: string[]
  favorite: boolean
  run_count: number
  updated_at: string
}

export interface ProductTemplate {
  id: string
  workspace_id?: string | null
  title: string
  description: string
  parameter_schema: Record<string, unknown>
  body: Record<string, unknown>
  current_version: number
  updated_at: string
}

export interface ProductNotification {
  id: string
  event_type: string
  title: string
  body: string
  metadata: Record<string, unknown>
  read_at?: string | null
  created_at: string
}

export interface ProductVersion {
  id: string
  resource_type: string
  resource_id: string
  version_number: number
  snapshot: Record<string, unknown>
  diff: Record<string, unknown>
  change_summary: string
  created_at: string
}

export interface ProductTeam {
  id: string
  org_id: string
  name: string
  created_at: string
}

export interface ProductAssistant {
  id: string
  org_id: string
  name: string
  description: string
  instructions: string
  capability_permissions: string[]
  status: string
  current_version: number
  metrics: Record<string, unknown>
  updated_at: string
}

export interface ProductIntegration {
  id: string
  org_id: string
  workspace_id?: string | null
  provider_key: string
  status: string
  health_status: string
  updated_at: string
}

export interface ProductIntegrationCatalogItem {
  provider_key: string
  name: string
  category: string
  auth_type: string
  status: string
}

export interface ProductPlan {
  plan_key: string
  name: string
  monthly_price_cents: number
  limits: Record<string, unknown>
  entitlements: Record<string, unknown>
}

export interface ProductSubscription {
  id: string
  org_id: string
  plan_key: string
  status: string
  seat_count: number
}

export interface ProductApiKey {
  id: string
  name: string
  key_preview: string
  scopes: string[]
  status: string
  usage_count: number
}

export interface ProductInvoice {
  id: string
  invoice_number: string
  status: string
  amount_due_cents: number
  issued_at: string
}

export interface ProductBudgetAlert {
  id: string
  name: string
  monthly_budget_cents: number
  threshold_percent: number
  status: string
}

export interface ProductSecurityPolicy {
  id: string
  name: string
  policy_type: string
  status: string
  current_version: number
}

export interface ProductComplianceExport {
  id: string
  export_type: string
  status: string
  artifact_ref: string
  created_at: string
}

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      // keep status fallback
    }
    throw new Error(detail)
  }
  return await res.json() as T
}

export function useProduct() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '')
  const [user, setUser] = useState<ProductUser | null>(null)
  const [orgs, setOrgs] = useState<ProductOrg[]>([])
  const [workspaces, setWorkspaces] = useState<ProductWorkspace[]>([])
  const [workflows, setWorkflows] = useState<ProductWorkflow[]>([])
  const [tasks, setTasks] = useState<ProductTask[]>([])
  const [templates, setTemplates] = useState<ProductTemplate[]>([])
  const [notifications, setNotifications] = useState<ProductNotification[]>([])
  const [selectedReplay, setSelectedReplay] = useState<ProductReplay | null>(null)
  const [versions, setVersions] = useState<ProductVersion[]>([])
  const [teams, setTeams] = useState<ProductTeam[]>([])
  const [assistants, setAssistants] = useState<ProductAssistant[]>([])
  const [integrationCatalog, setIntegrationCatalog] = useState<ProductIntegrationCatalogItem[]>([])
  const [integrations, setIntegrations] = useState<ProductIntegration[]>([])
  const [analytics, setAnalytics] = useState<Record<string, unknown> | null>(null)
  const [usage, setUsage] = useState<Record<string, unknown> | null>(null)
  const [plans, setPlans] = useState<ProductPlan[]>([])
  const [subscription, setSubscription] = useState<ProductSubscription | null>(null)
  const [apiKeys, setApiKeys] = useState<ProductApiKey[]>([])
  const [invoices, setInvoices] = useState<ProductInvoice[]>([])
  const [budgetAlerts, setBudgetAlerts] = useState<ProductBudgetAlert[]>([])
  const [entitlements, setEntitlements] = useState<Record<string, unknown> | null>(null)
  const [lastApiSecret, setLastApiSecret] = useState('')
  const [ssoConfig, setSsoConfig] = useState<Record<string, unknown> | null>(null)
  const [scimConfig, setScimConfig] = useState<Record<string, unknown> | null>(null)
  const [securityDashboard, setSecurityDashboard] = useState<Record<string, unknown> | null>(null)
  const [securityPolicies, setSecurityPolicies] = useState<ProductSecurityPolicy[]>([])
  const [complianceExports, setComplianceExports] = useState<ProductComplianceExport[]>([])
  const [adminPortal, setAdminPortal] = useState<Record<string, unknown> | null>(null)
  const [governanceDashboard, setGovernanceDashboard] = useState<Record<string, unknown> | null>(null)
  const [advancedAudit, setAdvancedAudit] = useState<Array<Record<string, unknown>>>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const authHeaders = useMemo(() => {
    const headers: Record<string, string> = {}
    if (token) headers.Authorization = `Bearer ${token}`
    return headers
  }, [token])

  const authedFetch = useCallback(async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...authHeaders,
    }
    return parseJson<T>(await fetch(`${BACKEND_URL}${path}`, {
      ...options,
      headers,
    }))
  }, [authHeaders])

  const refresh = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const [me, orgList, workspaceList, workflowList, taskList, templateList, notificationList, assistantList, catalogList, integrationList, planList, apiKeyList] = await Promise.all([
        authedFetch<ProductUser>('/v5/me'),
        authedFetch<ProductOrg[]>('/v5/orgs'),
        authedFetch<ProductWorkspace[]>('/v5/workspaces'),
        authedFetch<ProductWorkflow[]>('/v5/workflows?limit=20'),
        authedFetch<ProductTask[]>('/v5/tasks?limit=20'),
        authedFetch<ProductTemplate[]>('/v5/templates?limit=20'),
        authedFetch<ProductNotification[]>('/v5/notifications?limit=20'),
        authedFetch<ProductAssistant[]>('/v5/assistants?limit=20'),
        authedFetch<ProductIntegrationCatalogItem[]>('/v5/integrations/catalog'),
        authedFetch<ProductIntegration[]>('/v5/integrations/connections'),
        authedFetch<ProductPlan[]>('/v5/billing/plans'),
        authedFetch<ProductApiKey[]>('/v5/api-keys'),
      ])
      setUser(me)
      setOrgs(orgList)
      setWorkspaces(workspaceList)
      setWorkflows(workflowList)
      setTasks(taskList)
      setTemplates(templateList)
      setNotifications(notificationList)
      setAssistants(assistantList)
      setIntegrationCatalog(catalogList)
      setIntegrations(integrationList)
      setPlans(planList)
      setApiKeys(apiKeyList)
      if (orgList[0]) {
        const [teamList, analyticsData, usageData, subscriptionData, invoiceList, budgetList, entitlementData, ssoData, scimData, securityData, policyList, exportList, adminData, governanceData, auditData] = await Promise.all([
          authedFetch<ProductTeam[]>(`/v5/orgs/${orgList[0].id}/teams`),
          authedFetch<Record<string, unknown>>(`/v5/analytics?org_id=${orgList[0].id}`),
          authedFetch<Record<string, unknown>>(`/v5/usage?org_id=${orgList[0].id}`),
          authedFetch<ProductSubscription | null>(`/v5/billing/subscription?org_id=${orgList[0].id}`),
          authedFetch<ProductInvoice[]>(`/v5/billing/invoices?org_id=${orgList[0].id}`),
          authedFetch<ProductBudgetAlert[]>(`/v5/budget-alerts?org_id=${orgList[0].id}`),
          authedFetch<Record<string, unknown>>(`/v5/entitlements?org_id=${orgList[0].id}`),
          authedFetch<Record<string, unknown> | null>(`/v5/enterprise/sso?org_id=${orgList[0].id}`),
          authedFetch<Record<string, unknown> | null>(`/v5/enterprise/scim?org_id=${orgList[0].id}`),
          authedFetch<Record<string, unknown>>(`/v5/enterprise/security-dashboard?org_id=${orgList[0].id}`),
          authedFetch<ProductSecurityPolicy[]>(`/v5/enterprise/security-policies?org_id=${orgList[0].id}`),
          authedFetch<ProductComplianceExport[]>(`/v5/enterprise/compliance-exports?org_id=${orgList[0].id}`),
          authedFetch<Record<string, unknown>>(`/v5/enterprise/admin-portal?org_id=${orgList[0].id}`),
          authedFetch<Record<string, unknown>>(`/v5/enterprise/governance-dashboard?org_id=${orgList[0].id}`),
          authedFetch<Array<Record<string, unknown>>>(`/v5/enterprise/audit?org_id=${orgList[0].id}`),
        ])
        setTeams(teamList)
        setAnalytics(analyticsData)
        setUsage(usageData)
        setSubscription(subscriptionData)
        setInvoices(invoiceList)
        setBudgetAlerts(budgetList)
        setEntitlements(entitlementData)
        setSsoConfig(ssoData)
        setScimConfig(scimData)
        setSecurityDashboard(securityData)
        setSecurityPolicies(policyList)
        setComplianceExports(exportList)
        setAdminPortal(adminData)
        setGovernanceDashboard(governanceData)
        setAdvancedAudit(auditData)
      }
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [authedFetch, token])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const setAuth = useCallback((nextToken: string, nextUser: ProductUser) => {
    localStorage.setItem(TOKEN_KEY, nextToken)
    setToken(nextToken)
    setUser(nextUser)
  }, [])

  const register = useCallback(async (email: string, password: string, name: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await authedFetch<{ token: string, user: ProductUser }>('/v5/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password, name }),
      })
      setAuth(data.token, data.user)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [authedFetch, setAuth])

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await authedFetch<{ token: string, user: ProductUser }>('/v5/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
      setAuth(data.token, data.user)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [authedFetch, setAuth])

  const logout = useCallback(async () => {
    try {
      if (token) await authedFetch('/v5/auth/logout', { method: 'POST' })
    } catch {
      // local logout still wins
    }
    localStorage.removeItem(TOKEN_KEY)
    setToken('')
    setUser(null)
    setOrgs([])
    setWorkspaces([])
    setWorkflows([])
    setTasks([])
    setTemplates([])
    setNotifications([])
    setSelectedReplay(null)
    setVersions([])
    setTeams([])
    setAssistants([])
    setIntegrationCatalog([])
    setIntegrations([])
    setAnalytics(null)
    setUsage(null)
    setPlans([])
    setSubscription(null)
    setApiKeys([])
    setInvoices([])
    setBudgetAlerts([])
    setEntitlements(null)
    setLastApiSecret('')
    setSsoConfig(null)
    setScimConfig(null)
    setSecurityDashboard(null)
    setSecurityPolicies([])
    setComplianceExports([])
    setAdminPortal(null)
    setGovernanceDashboard(null)
    setAdvancedAudit([])
  }, [authedFetch, token])

  const createOrg = useCallback(async (name: string) => {
    const org = await authedFetch<ProductOrg>('/v5/orgs', { method: 'POST', body: JSON.stringify({ name }) })
    setOrgs((items) => [org, ...items])
    return org
  }, [authedFetch])

  const createWorkspace = useCallback(async (orgId: string, name: string) => {
    const workspace = await authedFetch<ProductWorkspace>('/v5/workspaces', { method: 'POST', body: JSON.stringify({ org_id: orgId, name }) })
    setWorkspaces((items) => [workspace, ...items])
    return workspace
  }, [authedFetch])

  const updatePreferences = useCallback(async (settings: Record<string, unknown>) => {
    const data = await authedFetch<{ preferences: Record<string, unknown> }>('/v5/me/preferences', { method: 'PATCH', body: JSON.stringify({ settings }) })
    setUser((current) => current ? { ...current, preferences: data.preferences } : current)
  }, [authedFetch])

  const loadReplay = useCallback(async (workflowId: string) => {
    const replay = await authedFetch<ProductReplay>(`/v5/workflows/${workflowId}/replay`)
    setSelectedReplay(replay)
    return replay
  }, [authedFetch])

  const shareReplay = useCallback(async (workflowId: string) => {
    return await authedFetch<Record<string, unknown>>(`/v5/workflows/${workflowId}/replay/share`, {
      method: 'POST',
      body: JSON.stringify({ visibility: 'workspace', redaction_policy: { secrets: true, credentials: true } }),
    })
  }, [authedFetch])

  const rerunWorkflow = useCallback(async (workflowId: string) => {
    const run = await authedFetch<ProductWorkflow>(`/v5/workflows/${workflowId}/rerun`, { method: 'POST' })
    setWorkflows((items) => [run, ...items])
    return run
  }, [authedFetch])

  const cloneWorkflow = useCallback(async (workflowId: string) => {
    const run = await authedFetch<ProductWorkflow>(`/v5/workflows/${workflowId}/clone`, { method: 'POST' })
    setWorkflows((items) => [run, ...items])
    return run
  }, [authedFetch])

  const createTask = useCallback(async (workspaceId: string, title: string, inputPrompt: string) => {
    const task = await authedFetch<ProductTask>('/v5/tasks', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: workspaceId || null, scope: workspaceId ? 'workspace' : 'personal', title, input_prompt: inputPrompt, tags: ['saved'] }),
    })
    setTasks((items) => [task, ...items])
    return task
  }, [authedFetch])

  const runTask = useCallback(async (taskId: string, workspaceId?: string) => {
    const run = await authedFetch<ProductWorkflow>(`/v5/tasks/${taskId}/run`, {
      method: 'POST',
      body: JSON.stringify({ workspace_id: workspaceId || null }),
    })
    setWorkflows((items) => [run, ...items])
    return run
  }, [authedFetch])

  const toggleTaskFavorite = useCallback(async (task: ProductTask) => {
    const updated = await authedFetch<ProductTask>(`/v5/tasks/${task.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ favorite: !task.favorite }),
    })
    setTasks((items) => items.map((item) => item.id === updated.id ? updated : item))
  }, [authedFetch])

  const createTemplate = useCallback(async (workspaceId: string, title: string, prompt: string) => {
    const template = await authedFetch<ProductTemplate>('/v5/templates', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: workspaceId, title, body: { prompt }, parameter_schema: { type: 'object', properties: {} } }),
    })
    setTemplates((items) => [template, ...items])
    return template
  }, [authedFetch])

  const runTemplate = useCallback(async (templateId: string) => {
    const run = await authedFetch<ProductWorkflow>(`/v5/templates/${templateId}/run`, {
      method: 'POST',
      body: JSON.stringify({ parameters: {} }),
    })
    setWorkflows((items) => [run, ...items])
    return run
  }, [authedFetch])

  const forkTemplate = useCallback(async (templateId: string, workspaceId?: string | null) => {
    const template = await authedFetch<ProductTemplate>(`/v5/templates/${templateId}/fork`, {
      method: 'POST',
      body: JSON.stringify({ workspace_id: workspaceId || null }),
    })
    setTemplates((items) => [template, ...items])
    return template
  }, [authedFetch])

  const loadVersions = useCallback(async (resourceType: string, resourceId: string) => {
    const data = await authedFetch<ProductVersion[]>(`/v5/versions/${resourceType}/${resourceId}`)
    setVersions(data)
    return data
  }, [authedFetch])

  const markNotificationRead = useCallback(async (notificationId: string) => {
    const updated = await authedFetch<ProductNotification>(`/v5/notifications/${notificationId}/read`, { method: 'POST' })
    setNotifications((items) => items.map((item) => item.id === updated.id ? updated : item))
  }, [authedFetch])

  const createTeam = useCallback(async (orgId: string, name: string) => {
    const team = await authedFetch<ProductTeam>(`/v5/orgs/${orgId}/teams`, { method: 'POST', body: JSON.stringify({ name }) })
    setTeams((items) => [team, ...items])
    return team
  }, [authedFetch])

  const inviteUser = useCallback(async (orgId: string, email: string, teamId?: string, workspaceId?: string) => {
    return await authedFetch<Record<string, unknown>>('/v5/invitations', {
      method: 'POST',
      body: JSON.stringify({ org_id: orgId, email, role: 'member', team_id: teamId || null, workspace_id: workspaceId || null }),
    })
  }, [authedFetch])

  const shareWorkspace = useCallback(async (workspaceId: string, teamId: string) => {
    return await authedFetch<Record<string, unknown>>(`/v5/workspaces/${workspaceId}/shares`, { method: 'POST', body: JSON.stringify({ team_id: teamId, role: 'member' }) })
  }, [authedFetch])

  const createAssistant = useCallback(async (orgId: string, name: string, instructions: string) => {
    const assistant = await authedFetch<ProductAssistant>('/v5/assistants', {
      method: 'POST',
      body: JSON.stringify({ org_id: orgId, name, instructions, capability_permissions: ['workflow.run', 'browser.observe'] }),
    })
    setAssistants((items) => [assistant, ...items])
    return assistant
  }, [authedFetch])

  const publishAssistant = useCallback(async (assistantId: string) => {
    const assistant = await authedFetch<ProductAssistant>(`/v5/assistants/${assistantId}/publish`, { method: 'POST' })
    setAssistants((items) => items.map((item) => item.id === assistant.id ? assistant : item))
  }, [authedFetch])

  const assignAssistant = useCallback(async (assistantId: string, workspaceId: string) => {
    return await authedFetch<Record<string, unknown>>(`/v5/assistants/${assistantId}/assignments`, { method: 'POST', body: JSON.stringify({ workspace_id: workspaceId, role: 'assistant' }) })
  }, [authedFetch])

  const connectIntegration = useCallback(async (orgId: string, providerKey: string, workspaceId?: string) => {
    const connection = await authedFetch<ProductIntegration>('/v5/integrations/connections', {
      method: 'POST',
      body: JSON.stringify({ org_id: orgId, provider_key: providerKey, workspace_id: workspaceId || null, token_metadata: { mode: 'stub' } }),
    })
    setIntegrations((items) => [connection, ...items])
    return connection
  }, [authedFetch])

  const checkIntegrationHealth = useCallback(async (connectionId: string) => {
    await authedFetch<Record<string, unknown>>(`/v5/integrations/connections/${connectionId}/health`, { method: 'POST', body: JSON.stringify({ status: 'healthy', latency_ms: 25, message: 'stub ok' }) })
    await refresh()
  }, [authedFetch, refresh])

  const recordUsage = useCallback(async (orgId: string, workspaceId?: string) => {
    await authedFetch<Record<string, unknown>>('/v5/usage/records', { method: 'POST', body: JSON.stringify({ org_id: orgId, workspace_id: workspaceId || null, usage_type: 'api_calls', quantity: 1, unit: 'request' }) })
    await refresh()
  }, [authedFetch, refresh])

  const subscribe = useCallback(async (orgId: string, planKey: string, seatCount: number) => {
    const data = await authedFetch<ProductSubscription>('/v5/billing/subscriptions', { method: 'POST', body: JSON.stringify({ org_id: orgId, plan_key: planKey, seat_count: seatCount, trial: planKey === 'free' }) })
    setSubscription(data)
    return data
  }, [authedFetch])

  const createInvoice = useCallback(async (orgId: string, amountDueCents: number) => {
    const invoice = await authedFetch<ProductInvoice>('/v5/billing/invoices', { method: 'POST', body: JSON.stringify({ org_id: orgId, amount_due_cents: amountDueCents, line_items: [{ label: 'Stub platform charges', amount_cents: amountDueCents }] }) })
    setInvoices((items) => [invoice, ...items])
    return invoice
  }, [authedFetch])

  const createApiKey = useCallback(async (orgId: string, workspaceId: string | undefined, name: string) => {
    const data = await authedFetch<{ api_key: ProductApiKey, secret: string }>('/v5/api-keys', { method: 'POST', body: JSON.stringify({ org_id: orgId, workspace_id: workspaceId || null, name, scopes: ['workflow:run', 'usage:read'] }) })
    setApiKeys((items) => [data.api_key, ...items])
    setLastApiSecret(data.secret)
    return data
  }, [authedFetch])

  const rotateApiKey = useCallback(async (keyId: string) => {
    const data = await authedFetch<{ api_key: ProductApiKey, secret: string }>(`/v5/api-keys/${keyId}/rotate`, { method: 'POST' })
    setApiKeys((items) => [data.api_key, ...items.map((item) => item.id === keyId ? { ...item, status: 'rotated' } : item)])
    setLastApiSecret(data.secret)
  }, [authedFetch])

  const revokeApiKey = useCallback(async (keyId: string) => {
    const key = await authedFetch<ProductApiKey>(`/v5/api-keys/${keyId}/revoke`, { method: 'POST' })
    setApiKeys((items) => items.map((item) => item.id === key.id ? key : item))
  }, [authedFetch])

  const createBudgetAlert = useCallback(async (orgId: string, workspaceId: string | undefined, name: string, monthlyBudgetCents: number) => {
    const alert = await authedFetch<ProductBudgetAlert>('/v5/budget-alerts', { method: 'POST', body: JSON.stringify({ org_id: orgId, workspace_id: workspaceId || null, name, monthly_budget_cents: monthlyBudgetCents, threshold_percent: 80 }) })
    setBudgetAlerts((items) => [alert, ...items])
    return alert
  }, [authedFetch])

  const configureSso = useCallback(async (orgId: string, domain: string) => {
    const data = await authedFetch<Record<string, unknown>>('/v5/enterprise/sso', { method: 'PATCH', body: JSON.stringify({ org_id: orgId, enforce_sso: true, domain_verification: { domain, status: 'stub_verified' }, saml_metadata: { entity_id: `stub:${domain}` }, oidc_metadata: {}, idp_metadata: { provider: 'stub' }, login_policy: { mode: 'sso_optional' } }) })
    setSsoConfig(data)
    return data
  }, [authedFetch])

  const configureScim = useCallback(async (orgId: string) => {
    const data = await authedFetch<Record<string, unknown>>('/v5/enterprise/scim', { method: 'PATCH', body: JSON.stringify({ org_id: orgId, base_url: 'https://scim.example.test/v2', bearer_token: 'stub-token', user_mapping: { email: 'userName' }, group_mapping: { name: 'displayName' }, provisioning_status: 'enabled' }) })
    setScimConfig(data)
    return data
  }, [authedFetch])

  const createSecurityPolicy = useCallback(async (orgId: string, workspaceId: string | undefined, name: string) => {
    const policy = await authedFetch<ProductSecurityPolicy>('/v5/enterprise/security-policies', { method: 'POST', body: JSON.stringify({ org_id: orgId, workspace_id: workspaceId || null, policy_type: 'session_timeout', name, rules: { timeout_minutes: 60, mfa_required: true } }) })
    setSecurityPolicies((items) => [policy, ...items])
    return policy
  }, [authedFetch])

  const createComplianceExport = useCallback(async (orgId: string, exportType: string) => {
    const item = await authedFetch<ProductComplianceExport>('/v5/enterprise/compliance-exports', { method: 'POST', body: JSON.stringify({ org_id: orgId, export_type: exportType, filters: { format: 'json' } }) })
    setComplianceExports((items) => [item, ...items])
    return item
  }, [authedFetch])

  const createRetentionRule = useCallback(async (orgId: string, workspaceId: string | undefined, dataType: string) => {
    return await authedFetch<Record<string, unknown>>('/v5/enterprise/retention-rules', { method: 'POST', body: JSON.stringify({ org_id: orgId, workspace_id: workspaceId || null, data_type: dataType, retention_days: 365, action: 'retain' }) })
  }, [authedFetch])

  const updateGovernance = useCallback(async (orgId: string) => {
    await authedFetch<Record<string, unknown>>('/v5/enterprise/governance/settings', { method: 'PATCH', body: JSON.stringify({ org_id: orgId, settings: { high_risk_requires_approval: true, v3_reuse: true } }) })
    await authedFetch<Record<string, unknown>>('/v5/enterprise/governance/workflows', { method: 'POST', body: JSON.stringify({ org_id: orgId, name: 'High risk approval', trigger_policy: { risk: 'high' }, approver_rules: { role: 'admin' } }) })
    await refresh()
  }, [authedFetch, refresh])

  return {
    token,
    user,
    orgs,
    workspaces,
    workflows,
    tasks,
    templates,
    notifications,
    selectedReplay,
    versions,
    teams,
    assistants,
    integrationCatalog,
    integrations,
    analytics,
    usage,
    plans,
    subscription,
    apiKeys,
    invoices,
    budgetAlerts,
    entitlements,
    lastApiSecret,
    ssoConfig,
    scimConfig,
    securityDashboard,
    securityPolicies,
    complianceExports,
    adminPortal,
    governanceDashboard,
    advancedAudit,
    loading,
    error,
    refresh,
    register,
    login,
    logout,
    createOrg,
    createWorkspace,
    updatePreferences,
    loadReplay,
    shareReplay,
    rerunWorkflow,
    cloneWorkflow,
    createTask,
    runTask,
    toggleTaskFavorite,
    createTemplate,
    runTemplate,
    forkTemplate,
    loadVersions,
    markNotificationRead,
    createTeam,
    inviteUser,
    shareWorkspace,
    createAssistant,
    publishAssistant,
    assignAssistant,
    connectIntegration,
    checkIntegrationHealth,
    recordUsage,
    subscribe,
    createInvoice,
    createApiKey,
    rotateApiKey,
    revokeApiKey,
    createBudgetAlert,
    configureSso,
    configureScim,
    createSecurityPolicy,
    createComplianceExport,
    createRetentionRule,
    updateGovernance,
  }
}
