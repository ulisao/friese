import { Route, Routes } from 'react-router-dom'

import { ForgotPasswordPage } from '@/pages/ForgotPasswordPage'
import { PrivacyPage, TermsPage } from '@/pages/LegalPages'
import { LoginPage } from '@/pages/LoginPage'
import { NewShipmentPage } from '@/pages/NewShipmentPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { RegisterOperatorPage } from '@/pages/RegisterOperatorPage'
import { ResetPasswordPage } from '@/pages/ResetPasswordPage'
import { ShipmentDetailPage } from '@/pages/ShipmentDetailPage'
import { ShipmentsPage } from '@/pages/ShipmentsPage'
import { ProtectedRoute } from '@/routes/ProtectedRoute'
import { isBootstrapping, useAuthStore } from '@/store/auth'
import { lazy, Suspense } from 'react'
const PublicShipmentPage = lazy(() =>
  import('@/pages/PublicShipmentPage').then((module) => ({ default: module.PublicShipmentPage }))
)

export default function App() {
  const bootstrapping = useAuthStore(isBootstrapping)

  // Mientras se revive la sesión guardada no se decide nada: si no, se vería un
  // flash de la pantalla de login antes de entrar.
  if (bootstrapping) {
    return (
      <main className="flex min-h-svh items-center justify-center p-4">
        <p className="text-sm text-muted-foreground">Cargando…</p>
      </main>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Alta del operador: es la URL que codifica el QR que genera el admin de
          la empresa (users/invites.py). Pública: el operador todavía no existe. */}
      <Route path="/alta-operador/:token" element={<RegisterOperatorPage />} />

      {/* Recuperación de contraseña (tarea 7.4). Públicas: el que se la olvidó no
          puede entrar. Las usan tanto el operador como el admin de empresa —a este
          último lo manda acá el login del panel de Django. */}
      <Route path="/recuperar-contrasena" element={<ForgotPasswordPage />} />
      <Route path="/restablecer/:uid/:token" element={<ResetPasswordPage />} />

      {/* Pantalla del receptor: pública, sin login. Es la ruta que arma
          emails.build_public_link() con el public_token del remito. */}
<Route
  path="/remito/:token"
  element={
    <Suspense fallback={<p className="text-sm text-muted-foreground">Cargando…</p>}>
      <PublicShipmentPage />
    </Suspense>
  }
/>
      {/* Términos y Privacidad (tarea 7.5). Públicas y sin login: las abre tanto el
          receptor desde el aviso de su pantalla (7.6) como el admin desde el pie del
          panel, y son las que enlaza la landing. */}
      <Route path="/terminos" element={<TermsPage />} />
      <Route path="/privacidad" element={<PrivacyPage />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<ShipmentsPage />} />
        <Route path="/remitos/nuevo" element={<NewShipmentPage />} />
        <Route path="/remitos/:id" element={<ShipmentDetailPage />} />
      </Route>

      {/* Ruta inválida: se muestra un 404 con la marca en vez de redirigir en
          silencio a "/" (tarea 10.4). Va última: matchea lo que no matchó antes. */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
