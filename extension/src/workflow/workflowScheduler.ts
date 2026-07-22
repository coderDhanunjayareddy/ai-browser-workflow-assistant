export type ScheduledWorkStatus = 'pending' | 'running' | 'delayed' | 'completed' | 'failed' | 'cancelled'

export interface ScheduledWorkItem {
  schema_version: 'scheduled_work_item.v1'
  id: string
  run_id: string
  kind: string
  status: ScheduledWorkStatus
  dependency_ids: string[]
  earliest_start_at: string
  attempt: number
  max_attempts: number
}

export class WorkflowScheduler {
  private readonly items = new Map<string, ScheduledWorkItem>()

  enqueue(item: ScheduledWorkItem): ScheduledWorkItem {
    this.items.set(item.id, item)
    return item
  }

  get(itemId: string): ScheduledWorkItem | undefined {
    return this.items.get(itemId)
  }

  list(): ScheduledWorkItem[] {
    return Array.from(this.items.values())
  }
}
