import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { requestPasswordReset } from '@/lib/api'

/*
 * Paso 1 de la recuperación de contraseña (tarea 7.4): a dónde mandamos el link.
 *
 * Es la misma pantalla para el operador y para el admin de empresa: al admin lo
 * trae acá el link "¿Perdiste tu contraseña?" del login del panel (config/urls.py).
 *
 * El backend contesta SIEMPRE lo mismo, exista o no el usuario, así que esta
 * pantalla también: si mostrara "ese usuario no existe", cualquiera podría
 * averiguar qué usuarios hay.
 */
export function ForgotPasswordPage() {
  const [identifier, setIdentifier] = useState('')
  const [enviado, setEnviado] = useState(false)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      const { data } = await requestPasswordReset({ identifier })
      setEnviado(data.detail)
    } catch (requestError) {
      setError(
        requestError.response?.status === 429
          ? 'Probaste demasiadas veces seguidas. Esperá un rato y volvé a intentar.'
          : 'No se pudo conectar con el servidor. Intentá de nuevo.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="justify-items-center text-center">
          <img src="/friese-logo.png" alt="Friese" width="96" height="99" className="mx-auto w-24" />
          <CardTitle className="sr-only">Recuperar contraseña</CardTitle>
          <CardDescription>
            {enviado
              ? 'Revisá tu casilla de email.'
              : 'Decinos quién sos y te mandamos un link por email para elegir una contraseña nueva.'}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {enviado ? (
            <div className="flex flex-col gap-4">
              <p role="status" data-testid="reset-sent" className="text-sm text-muted-foreground">
                {enviado}
              </p>
              <Button asChild variant="outline" className="h-12 w-full">
                <Link to="/login">Volver al login</Link>
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="identifier">Usuario o email</Label>
                <Input
                  id="identifier"
                  name="identifier"
                  autoComplete="username"
                  autoCapitalize="none"
                  autoFocus
                  required
                  className="h-12"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Si no tenés un email cargado en tu usuario, pedile a tu encargado que te lo
                  cargue desde el panel.
                </p>
              </div>

              {error && (
                <p role="alert" data-testid="forgot-error" className="text-sm text-destructive">
                  {error}
                </p>
              )}

              <Button type="submit" className="h-12 w-full" disabled={submitting}>
                {submitting ? 'Enviando…' : 'Enviarme el link'}
              </Button>

              <Button asChild variant="ghost" className="h-10 w-full">
                <Link to="/login">Volver al login</Link>
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
