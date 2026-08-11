import { Navigate, Route, Routes } from 'react-router-dom'

import { LoginPage } from '@/pages/LoginPage'
import { NewShipmentPage } from '@/pages/NewShipmentPage'
import { ShipmentDetailPage } from '@/pages/ShipmentDetailPage'
import { ShipmentsPage } from '@/pages/ShipmentsPage'
import { ProtectedRoute } from '@/routes/ProtectedRoute'
import { isBootstrapping, useAuthStore } from '@/store/auth'
import { lazy, Suspense } from 'react'
const PublicShipmentPage = lazy(() => import('@/pages/PublicShipmentPage'))

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
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<ShipmentsPage />} />
        <Route path="/remitos/nuevo" element={<NewShipmentPage />} />
        <Route path="/remitos/:id" element={<ShipmentDetailPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
