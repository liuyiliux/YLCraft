import { describe, expect, it } from 'vitest'

import {
  pickDefaultConnector,
  resolveDefaultModel,
  resolveModelCandidates,
  resolveModelSelection,
} from '../../utils/modelSelection'

describe('resolveModelSelection', () => {
  it('prefers the connector default model over a stale available_models list', () => {
    const backend = { model: 'agnes-video-2.5-flash', available_models: ['agnes-video-v2.0'] }
    expect(resolveModelSelection(backend)).toBe('agnes-video-2.5-flash')
  })

  it('accepts default_model as the default-model field (/ai/connectors)', () => {
    // 2026-10-31 迁移角色详情页时踩到：只认 model 会退回 available_models[0]
    expect(
      resolveModelSelection({ default_model: 'gpt-5.5', available_models: ['gpt-4o'] }),
    ).toBe('gpt-5.5')
  })

  it('prefers model when both field names are present', () => {
    expect(resolveModelSelection({ model: 'a', default_model: 'b' })).toBe('a')
    expect(resolveDefaultModel({ model: 'a', default_model: 'b' })).toBe('a')
    expect(resolveDefaultModel({ default_model: 'b' })).toBe('b')
  })

  it('falls back to the first available model when no default model is declared', () => {
    expect(resolveModelSelection({ model: '', available_models: ['a', 'b'] })).toBe('a')
    expect(resolveModelSelection({ available_models: ['a', 'b'] })).toBe('a')
  })

  it('uses the default model alone for legacy backends without available_models', () => {
    expect(resolveModelSelection({ model: 'm' })).toBe('m')
    expect(resolveModelSelection({ default_model: 'm2' })).toBe('m2')
  })

  it('returns empty string for a missing backend or no usable model', () => {
    expect(resolveModelSelection(undefined)).toBe('')
    expect(resolveModelSelection({})).toBe('')
    expect(resolveModelSelection({ model: '  ', available_models: [] })).toBe('')
    expect(resolveDefaultModel(undefined)).toBe('')
  })
})

describe('resolveModelCandidates', () => {
  it('puts the default model first even when the list conflicts', () => {
    const backend = { model: 'agnes-video-2.5-flash', available_models: ['agnes-video-v2.0'] }
    expect(resolveModelCandidates(backend)).toEqual([
      'agnes-video-2.5-flash',
      'agnes-video-v2.0',
    ])
  })

  it('includes default_model in the candidates', () => {
    expect(
      resolveModelCandidates({ default_model: 'gpt-5.5', available_models: ['gpt-4o'] }),
    ).toEqual(['gpt-5.5', 'gpt-4o'])
  })

  it('de-duplicates when the list already contains the model', () => {
    expect(
      resolveModelCandidates({ model: 'm', available_models: ['m', 'n', 'm'] }),
    ).toEqual(['m', 'n'])
  })

  it('uses available_models when no default model and drops empty values', () => {
    expect(
      resolveModelCandidates({ model: '', available_models: ['', 'a', '  ', 'a', 'b'] }),
    ).toEqual(['a', 'b'])
  })

  it('returns only the default model for legacy backends', () => {
    expect(resolveModelCandidates({ model: 'm' })).toEqual(['m'])
  })

  it('returns an empty list for a missing backend', () => {
    expect(resolveModelCandidates(undefined)).toEqual([])
  })
})

describe('pickDefaultConnector', () => {
  // 2026-11-01 事故：列表第一个是没启动的本地反代（127.0.0.1:8317），
  // 用户标记为默认的连接器排在后面 → AI 补全报 All connection attempts failed。
  const localProxy = { name: '本地反代', is_default: false }
  const markedDefault = { name: '若海-qwen3.8-27b', is_default: true }
  const other = { name: 'aaccx-gtp-5.5', is_default: false }

  it('prefers the connector the user marked as default', () => {
    expect(pickDefaultConnector([localProxy, markedDefault, other])).toBe(markedDefault)
  })

  it('falls back to the first connector when none is marked', () => {
    expect(pickDefaultConnector([localProxy, other])).toBe(localProxy)
  })

  it('returns null for empty or missing lists', () => {
    expect(pickDefaultConnector([])).toBeNull()
    expect(pickDefaultConnector(undefined)).toBeNull()
    expect(pickDefaultConnector(null)).toBeNull()
  })
})
