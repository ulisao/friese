import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { login } from '@/lib/api'
import { isAuthenticated, useAuthStore } from '@/store/auth'

// El login del operador es SIEMPRE individual: usuario + contraseña propios,
// nunca un login compartido por dispositivo (docs/desarrollo.md sección 4).
export function LoginPage() {
  const authenticated = useAuthStore(isAuthenticated)
  const setSession = useAuthStore((state) => state.setSession)
  const navigate = useNavigate()
  const location = useLocation()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (authenticated) {
    return <Navigate to={location.state?.from ?? '/'} replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      const { data } = await login({ username, password })
      setSession({ access: data.access, refresh: data.refresh, username })
      navigate(location.state?.from ?? '/', { replace: true })
    } catch (requestError) {
      setError(
        requestError.response?.status === 401
          ? 'Usuario o contraseña incorrectos.'
          : 'No se pudo conectar con el servidor. Intentá de nuevo.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-2xl font-semibold">Friese</CardTitle>
          <CardDescription>Ingresá con tu usuario de operador.</CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="username">Usuario</Label>
              <Input
                id="username"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                autoFocus
                required
                className="h-12"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Contraseña</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                className="h-12"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}

            <Button type="submit" className="h-12 w-full" disabled={submitting}>
              {submitting ? 'Ingresando…' : 'Ingresar'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
