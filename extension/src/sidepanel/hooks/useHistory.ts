import { useState, useCallback } from 'react'
import type { SessionHistory } from '../../types'

const BACKEND_URL = 'http://localhost:8000'

export function useHistory() {
  const [sessions, setSessions] = useState<SessionHistory[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchHistory = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${BACKEND_URL}/workflow/history?limit=20`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: { sessions: SessionHistory[]; total: number } = await res.json()
      setSessions(data.sessions)
    } catch (err) {
      setError(`Could not load history: ${String(err)}`)
    } finally {
      setLoading(false)
    }
  }, [])

  return { sessions, loading, error, fetchHistory }
}
