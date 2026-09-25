const STATUS_ALIAS_MAP: Record<string, string> = {
  completed: 'done',
  succeeded: 'done',
  success: 'done',
  processing: 'running',
  downloading: 'running',
  queued: 'pending',
  canceled: 'cancelled',
  cancel: 'cancelled',
  error: 'failed',
}

export function normalizeTaskStatus(status: string) {
  const normalized = String(status || '').toLowerCase()
  return STATUS_ALIAS_MAP[normalized] || normalized
}
