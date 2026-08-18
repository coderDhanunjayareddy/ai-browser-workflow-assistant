declare const __BACKEND_URL__: string | undefined

const configuredBackendUrl = typeof __BACKEND_URL__ === 'string' ? __BACKEND_URL__.trim() : ''

export const BACKEND_URL = (configuredBackendUrl || 'http://localhost:8000').replace(/\/$/, '')
