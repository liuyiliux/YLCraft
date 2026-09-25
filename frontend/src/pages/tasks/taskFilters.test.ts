import { describe, expect, it } from 'vitest'

import { normalizeTaskStatus } from './taskFilters'

describe('normalizeTaskStatus', () => {
  it('keeps canonical task statuses', () => {
    expect(normalizeTaskStatus('pending')).toBe('pending')
    expect(normalizeTaskStatus('running')).toBe('running')
    expect(normalizeTaskStatus('done')).toBe('done')
    expect(normalizeTaskStatus('failed')).toBe('failed')
    expect(normalizeTaskStatus('cancelled')).toBe('cancelled')
  })

  it('groups historical aliases into the status filter buckets', () => {
    expect(normalizeTaskStatus('completed')).toBe('done')
    expect(normalizeTaskStatus('succeeded')).toBe('done')
    expect(normalizeTaskStatus('success')).toBe('done')
    expect(normalizeTaskStatus('processing')).toBe('running')
    expect(normalizeTaskStatus('downloading')).toBe('running')
    expect(normalizeTaskStatus('queued')).toBe('pending')
    expect(normalizeTaskStatus('cancel')).toBe('cancelled')
    expect(normalizeTaskStatus('canceled')).toBe('cancelled')
    expect(normalizeTaskStatus('error')).toBe('failed')
  })

  it('normalizes case and empty values without inventing a status', () => {
    expect(normalizeTaskStatus('DONE')).toBe('done')
    expect(normalizeTaskStatus('')).toBe('')
  })
})
