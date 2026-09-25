import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { getCurrentUser, loginUser, logoutUser, registerUser, type AuthUser } from '../api'

type Credentials = { username: string; password: string }
type Registration = Credentials & { display_name?: string; email?: string }

type AuthContextValue = {
  user: AuthUser | null
  isLoading: boolean
  login: (credentials: Credentials) => Promise<AuthUser>
  register: (registration: Registration) => Promise<AuthUser>
  logout: () => Promise<void>
  refresh: () => Promise<AuthUser | null>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function isUnauthorized(error: unknown) {
  return (error as { status?: number } | undefined)?.status === 401
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const result = await getCurrentUser()
      setUser(result.data)
      return result.data
    } catch (error) {
      if (!isUnauthorized(error)) console.warn('[auth] Unable to restore session', error)
      setUser(null)
      return null
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const login = useCallback(async (credentials: Credentials) => {
    const result = await loginUser(credentials)
    setUser(result.data)
    return result.data
  }, [])

  const register = useCallback(async (registration: Registration) => {
    await registerUser(registration)
    return login({ username: registration.username, password: registration.password })
  }, [login])

  const logout = useCallback(async () => {
    try {
      await logoutUser()
    } finally {
      setUser(null)
    }
  }, [])

  const value = useMemo(() => ({ user, isLoading, login, register, logout, refresh }), [user, isLoading, login, register, logout, refresh])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within AuthProvider')
  return value
}
