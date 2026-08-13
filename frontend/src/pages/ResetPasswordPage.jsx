import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { confirmPasswordReset } from '@/lib/api'

/*
 * Paso 2 de la recuperación de contraseña (tarea 7.4): elegir la nueva.
 *
 * Es la pantalla a la que lleva el link del email. El par uid + token viaja en la
 * URL y lo valida el backend (users/password_reset.py): el link vence a las 24hs
 * y sirve UNA sola vez, porque el token se firma con la contraseña vieja.
 *
 * No se loguea sola al terminar: cambiar la contraseña cierra las sesiones
 * abiertas de ese usuario, así que entrar de nuevo es parte del flujo. Además el
 * admin de empresa entra por el panel, no por acá.
 */
export function ResetPasswordPage() {
  const { uid, token } = useParams()

  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [listo, setListo] = useState(false)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    if (password !== passwordConfirm) {
      setError('Las dos contraseñas no coinciden.')
      return
    }

    setSubmitting(true)
    try {
      await confirmPasswordReset({ uid, token, password })
      setListo(true)
    } catch (requestError) {
      if (requestError.response?.status === 429) {
        setError('Probaste demasiadas veces seguidas. Esperá un rato y volvé a intentar.')
        setSubmitting(false)
        return
      }
      // El backend explica el motivo real (link vencido o ya usado, contraseña
      // demasiado corta o común): se muestra tal cual, que es más útil que un
      // mensaje genérico. Los errores de DRF vienen por campo.
      const data = requestError.response?.data
      const detalle =
        data && typeof data === 'object'
          ? Object.values(data).flat().filter(Boolean).join(' ')
          : null
      setError(detalle || 'No se pudo cambiar la contraseña. Intentá de nuevo.')
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="justify-items-center text-center">
          <img src="/friese-logo.png" alt="Friese" width="96" height="99" className="mx-auto w-24" />
          <CardTitle className="sr-only">Elegir una contraseña nueva</CardTitle>
          <CardDescription>
            {listo ? 'Tu contraseña quedó actualizada.' : 'Elegí tu contraseña nueva.'}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {listo ? (
            <div className="flex flex-col gap-4">
              <p role="status" data-testid="reset-done" className="text-sm text-muted-foreground">
                Ya podés entrar con la contraseña nueva. Si administrás tu empresa desde el panel,
                entrá ahí como siempre.
              </p>
              <Button asChild className="h-12 w-full">
                <Link to="/login">Ir al login</Link>
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="password">Contraseña nueva</Label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  autoFocus
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
                <p role="alert" data-testid="reset-error" className="text-sm text-destructive">
                  {error}
                </p>
              )}

              <Button type="submit" className="h-12 w-full" disabled={submitting}>
                {submitting ? 'Guardando…' : 'Guardar la contraseña'}
              </Button>

              <Button asChild variant="ghost" className="h-10 w-full">
                <Link to="/recuperar-contrasena">Pedir un link nuevo</Link>
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
