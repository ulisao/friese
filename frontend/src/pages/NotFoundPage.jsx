import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { SUPPORT_EMAIL, SUPPORT_WHATSAPP_URL } from '@/lib/support'
import { useDocumentTitle } from '@/lib/useDocumentTitle'

/*
 * 404 del frontend (tarea 10.4).
 *
 * Antes el catch-all de App.jsx redirigía a "/" en silencio: quien abría un link
 * cortado terminaba en la lista de remitos sin enterarse de que la dirección estaba
 * mal, y si además no tenía sesión, en el login. Ahora la ruta inválida se dice.
 *
 * Es pública: la ve tanto el operador logueado como el receptor que copió mal el
 * link del email. Por eso el botón principal manda a "/" —que si hay sesión es la
 * lista y si no, el login— y el texto habla de las dos situaciones.
 */
export function NotFoundPage() {
  useDocumentTitle('Página no encontrada')
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-md flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="text-xs tracking-widest text-muted-foreground">ERROR 404</p>
      <h1 className="text-xl font-semibold">Esta página no existe</h1>
      <p className="text-sm text-muted-foreground" data-testid="notfound-message">
        La dirección que abriste no corresponde a ninguna pantalla de Friese. Puede que el link
        esté cortado o que se haya copiado de más.
      </p>
      <p className="text-sm text-muted-foreground">
        Si llegaste desde un email con el link de un remito, abrilo de nuevo desde ahí: ese link
        es único y no se puede escribir a mano.
      </p>
      <Button asChild className="h-12 w-full">
        <Link to="/">Volver al inicio</Link>
      </Button>
      <p className="text-sm text-muted-foreground">
        ¿Necesitás una mano? Escribinos por{' '}
        <a className="underline" href={SUPPORT_WHATSAPP_URL}>
          WhatsApp
        </a>{' '}
        o a{' '}
        <a className="underline" href={`mailto:${SUPPORT_EMAIL}`}>
          {SUPPORT_EMAIL}
        </a>
        .
      </p>
    </main>
  )
}
