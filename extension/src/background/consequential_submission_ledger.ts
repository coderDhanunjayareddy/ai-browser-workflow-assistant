import type { CanonicalActionContract, ConsequentialSubmissionDeclaration } from '../types'

export const SUBMISSION_LEDGER_KEY = 'consequential_submission_ledger_v1'

export type SubmissionLedgerState = 'reserved' | 'dispatching' | 'delivered' | 'uncertain'

export type SubmissionLedgerRecord = {
  submission_id: string
  idempotency_key: string
  state: SubmissionLedgerState
  origin: string
  destination_entity: string
  content_identity: string
  operation: string
  attempts: 1
  updated_at_ms: number
}

export type SubmissionStorage = {
  get(key: string): Promise<Record<string, unknown>>
  set(items: Record<string, unknown>): Promise<void>
}

export class ConsequentialSubmissionLedger {
  private queue: Promise<void> = Promise.resolve()

  constructor(private readonly storage: SubmissionStorage) {}

  async reserve(
    contract: Pick<CanonicalActionContract, 'idempotency_key' | 'origin'>,
    declaration: ConsequentialSubmissionDeclaration,
    now = Date.now(),
  ): Promise<{ allowed: true } | { allowed: false; reason: 'already_delivered' | 'uncertain_prior_dispatch' }> {
    const previous = this.queue
    let release!: () => void
    this.queue = new Promise<void>((resolve) => { release = resolve })
    await previous
    try {
      const stored = await this.storage.get(SUBMISSION_LEDGER_KEY)
      const records = (stored[SUBMISSION_LEDGER_KEY] || {}) as Record<string, SubmissionLedgerRecord>
      const existing = records[declaration.submission_id]
      if (existing) {
        return { allowed: false, reason: existing.state === 'delivered' ? 'already_delivered' : 'uncertain_prior_dispatch' }
      }
      records[declaration.submission_id] = {
        submission_id: declaration.submission_id,
        idempotency_key: contract.idempotency_key,
        state: 'reserved',
        origin: contract.origin.origin,
        destination_entity: declaration.destination_entity,
        content_identity: declaration.content_identity,
        operation: declaration.operation,
        attempts: 1,
        updated_at_ms: now,
      }
      await this.storage.set({ [SUBMISSION_LEDGER_KEY]: records })
      return { allowed: true }
    } finally {
      release()
    }
  }

  async settle(submissionId: string, state: SubmissionLedgerState, now = Date.now()): Promise<void> {
    const stored = await this.storage.get(SUBMISSION_LEDGER_KEY)
    const records = (stored[SUBMISSION_LEDGER_KEY] || {}) as Record<string, SubmissionLedgerRecord>
    const existing = records[submissionId]
    if (!existing) return
    records[submissionId] = { ...existing, state, updated_at_ms: now }
    await this.storage.set({ [SUBMISSION_LEDGER_KEY]: records })
  }
}
