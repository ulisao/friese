import axios from 'axios'

import { readStoredRefreshToken, useAuthStore } from '@/store/auth'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

// Cliente para todas las llamadas autenticadas de la app.
export const api = axios.create({
  baseURL: `${import.meta.env.VITE_API_URL}/api`,
  // ...
})

// El refresh se hace con un axios "pelado" para no volver a pasar por el
// interceptor de abajo (si no, un 401 del refresh dispararía otro refresh).
const plainClient = axios.create({ baseURL: API_BASE_URL })

/*
 * Cliente del flujo PÚBLICO del receptor (tareas 3.1/3.2): sin Authorization y sin
 * el interceptor de refresh. El receptor no tiene sesión, y la única credencial de
 * esos endpoints es el public_token de la URL. Va aparte a propósito: si el link se
 * abriera en el navegador de un operador logueado, no hay que mandarle su token a un
 * endpoint público ni disparar un refresh por un error de ese flujo.
 */
export const publicApi = axios.create({ baseURL: API_BASE_URL })

export function login({ username, password }) {
  return plainClient.post('/auth/login/', { username, password })
}

// Cada request sale con el access token que haya en el store en ese momento.
api.interceptors.request.use((config) => {
  const { accessToken } = useAuthStore.getState()
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  return config
})

// Si varias requests fallan con 401 a la vez, comparten un único refresh en vuelo.
let refreshInFlight = null

function refreshAccessToken() {
  // localStorage manda sobre el store: si hay otra pestaña abierta, ella pudo
  // haber rotado el refresh y el de esta pestaña ya estaría blacklisteado.
  const refreshToken = readStoredRefreshToken() ?? useAuthStore.getState().refreshToken
  if (!refreshToken) {
    return Promise.reject(new Error('No hay refresh token disponible.'))
  }

  if (!refreshInFlight) {
    refreshInFlight = plainClient
      .post('/auth/refresh/', { refresh: refreshToken })
      .then(({ data }) => {
        useAuthStore.getState().setTokens({ access: data.access, refresh: data.refresh })
        return data.access
      })
      .finally(() => {
        refreshInFlight = null
      })
  }

  return refreshInFlight
}

/*
 * Al abrir la app: si quedó un refresh token guardado, se canjea por un access
 * token nuevo para revivir la sesión sin pasar por el login. Si el refresh ya
 * expiró o está blacklisteado, se limpia y la app arranca en el login.
 */
export async function restoreSession() {
  if (useAuthStore.getState().status !== 'bootstrapping') return

  try {
    await refreshAccessToken()
  } catch {
    useAuthStore.getState().clearSession()
  }
}

/*
 * Interceptor de refresh (docs/desarrollo.md sección 4):
 * a) detecta el 401 por access token expirado,
 * b) renueva contra POST /api/auth/refresh/ y reintenta la request original,
 * c) si el refresh también expiró o está blacklisteado, limpia la sesión y las
 *    rutas protegidas redirigen al login.
 */
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { config, response } = error

    // Solo el 401 se reintenta, y una sola vez por request.
    if (!config || response?.status !== 401 || config._retriedAfterRefresh) {
      throw error
    }
    config._retriedAfterRefresh = true

    let accessToken
    try {
      accessToken = await refreshAccessToken()
    } catch {
      useAuthStore.getState().clearSession()
      throw error
    }

    config.headers.Authorization = `Bearer ${accessToken}`
    return api(config)
  },
)
