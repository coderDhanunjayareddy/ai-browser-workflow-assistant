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
      const [me, orgList, workspaceList, workflowList, taskList, templateList, notificationList] = await Promise.all([
        authedFetch<ProductUser>('/v5/me'),
        authedFetch<ProductOrg[]>('/v5/orgs'),
        authedFetch<ProductWorkspace[]>('/v5/workspaces'),
        authedFetch<ProductWorkflow[]>('/v5/workflows?limit=20'),
        authedFetch<ProductTask[]>('/v5/tasks?limit=20'),
        authedFetch<ProductTemplate[]>('/v5/templates?limit=20'),
        authedFetch<ProductNotification[]>('/v5/notifications?limit=20'),
      ])
      setUser(me)
      setOrgs(orgList)
      setWorkspaces(workspaceList)
      setWorkflows(workflowList)
      setTasks(taskList)
      setTemplates(templateList)
      setNotifications(notificationList)
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
  }
}
