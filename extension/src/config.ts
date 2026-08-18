declare const __BACKEND_URL__: string | undefined
declare const __APP_VERSION__: string | undefined
declare const __BUILD_COMMIT__: string | undefined
declare const __BUILD_ID__: string | undefined

const configuredBackendUrl = typeof __BACKEND_URL__ === 'string' ? __BACKEND_URL__.trim() : ''

export const BACKEND_URL = (configuredBackendUrl || 'http://localhost:8000').replace(/\/$/, '')
export const APP_VERSION = typeof __APP_VERSION__ === 'string' && __APP_VERSION__.trim() ? __APP_VERSION__.trim() : '0.4.0'
export const BUILD_COMMIT = typeof __BUILD_COMMIT__ === 'string' && __BUILD_COMMIT__.trim() ? __BUILD_COMMIT__.trim() : 'dev'
export const BUILD_ID = typeof __BUILD_ID__ === 'string' && __BUILD_ID__.trim() ? __BUILD_ID__.trim() : 'local-dev'
