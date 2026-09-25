import { afterEach, describe, expect, it, vi } from 'vitest'
import { getCurrentUser, loginUser, registerUser } from './index'

const fetchMock = vi.fn()

afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('local account API client', () => {
  it('restores the current user with session cookies', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ success: true, data: { id: 'u1', username: 'writer' } })))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getCurrentUser()).resolves.toMatchObject({ data: { id: 'u1' } })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/me', expect.objectContaining({ credentials: 'include' }))
  })

  it('sends account credentials as JSON while allowing the server to set an HttpOnly cookie', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ success: true, data: { id: 'u1', username: 'writer' } })))
    vi.stubGlobal('fetch', fetchMock)

    await loginUser({ username: 'writer', password: 'password123' })
    await registerUser({ username: 'new_writer', password: 'password123', display_name: 'Writer' })

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/auth/login', expect.objectContaining({
      method: 'POST', credentials: 'include', body: JSON.stringify({ username: 'writer', password: 'password123' }),
    }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/auth/register', expect.objectContaining({
      method: 'POST', credentials: 'include', body: JSON.stringify({ username: 'new_writer', password: 'password123', display_name: 'Writer' }),
    }))
  })
})
