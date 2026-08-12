import { useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { login, registerOperator } from '@/lib/api'
import { isAuthenticated, useAuthStore } from '@/store/auth'

/*
 * Alta inicial del operador: es la pantalla a la que lleva el QR que le muestra
 * el admin de su empresa (docs/desarrollo.md sección 3). El token viaja en la URL.
 *
 * El QR se usa UNA sola vez, para el alta; nunca como login recurrente (sección 4).
 * Por eso, creada la cuenta, se entra con usuario y contraseña como siempre.
 */
export function RegisterOperatorPage() {
  const { token } = useParams()
  const authenticated = useAuthStore(isAuthenticated)
  const setSession = useAuthStore((state) => state.setSession)
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (authenticated) {
    return <Navigate to="/" replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    if (password !== passwordConfirm) {
      setError('Las dos contraseñas no coinciden.')
      return
    }

    setSubmitting(true)
    try {
      await registerOperator({ token, username, password })
    } catch (requestError) {
      // El backend explica el motivo real (invitación usada, vencida, usuario
      // repetido, contraseña débil): se muestra tal cual, que es más útil que un
      // mensaje genérico. Los errores de DRF vienen por campo.
      const data = requestError.response?.data
      const detalle =
        data && typeof data === 'object'
          ? Object.values(data).flat().filter(Boolean).join(' ')
          : null
      setError(
        detalle ||
          'No se pudo crear la cuenta. Pedile a tu encargado un código nuevo.',
      )
      setSubmitting(false)
      return
    }

    // Cuenta creada: se entra sola, así el operador no tipea lo mismo dos veces.
    // Si el login fallara igual la cuenta ya existe, así que se lo manda al login
    // en vez de dejarlo trabado en esta pantalla.
    try {
      const { data } = await login({ username, password })
      setSession({ access: data.access, username })
      navigate('/', { replace: true })
    } catch {
      navigate('/login', { replace: true })
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="justify-items-center text-center">
          <img src="/friese-logo.png" alt="Friese" width="96" height="99" className="mx-auto w-24" />
          <CardTitle className="sr-only">Friese</CardTitle>
          <CardDescription>
            Creá tu usuario de operador. Vas a usarlo cada vez que entres.
          </CardDescription>
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
                autoComplete="new-password"
                required
                className="h-12"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="password-confirm">Repetí la contraseña</Label>
              <Input
                id="password-confirm"
                name="password_confirm"
                type="password"
                autoComplete="new-password"
                required
                className="h-12"
                value={passwordConfirm}
                onChange={(event) => setPasswordConfirm(event.target.value)}
              />
            </div>

            {error && (
              <p role="alert" data-testid="register-error" className="text-sm text-destructive">
                {error}
              </p>
            )}

            <Button type="submit" className="h-12 w-full" disabled={submitting}>
              {submitting ? 'Creando tu usuario…' : 'Crear mi usuario'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
