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
      const [me, orgList, workspaceList, workflowList, taskList, templateList, notificationList, assistantList, catalogList, integrationList] = await Promise.all([
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
      if (orgList[0]) {
        const [teamList, analyticsData, usageData] = await Promise.all([
          authedFetch<ProductTeam[]>(`/v5/orgs/${orgList[0].id}/teams`),
          authedFetch<Record<string, unknown>>(`/v5/analytics?org_id=${orgList[0].id}`),
          authedFetch<Record<string, unknown>>(`/v5/usage?org_id=${orgList[0].id}`),
        ])
        setTeams(teamList)
        setAnalytics(analyticsData)
        setUsage(usageData)
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
  }
}
