import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { isAuthenticated, useAuthStore } from '@/store/auth'

// Sin sesión en el store no se entra: se manda al login. Como el interceptor
// limpia el store cuando el refresh falla, esto también cubre el caso (c) de la
// sección 4: refresh expirado o blacklisteado → login.
export function ProtectedRoute() {
  const authenticated = useAuthStore(isAuthenticated)
  const location = useLocation()

  if (!authenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return <Outlet />
}
