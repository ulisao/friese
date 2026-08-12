import axios from 'axios'

import { useAuthStore } from '@/store/auth'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

// Cliente para todas las llamadas autenticadas de la app.
export const api = axios.create({ baseURL: API_BASE_URL })

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

/*
 * Login: la respuesta trae SOLO el access token. El refresh vuelve en una cookie
 * httpOnly que pone el backend (tarea 6.7), así que hay que pedir explícitamente
 * que la request lleve/acepte credenciales: sin `withCredentials` el navegador
 * descarta el Set-Cookie cuando la API está en otro origen.
 */
export function login({ username, password }) {
  return plainClient.post('/auth/login/', { username, password }, { withCredentials: true })
}

/*
 * Logout: el backend blacklistea el refresh de la cookie y la borra. Se llama
 * siempre con credenciales, porque la cookie ES el dato que necesita.
 */
export function logout() {
  return plainClient.post('/auth/logout/', null, { withCredentials: true })
}

// Alta inicial del operador con el token del QR (sección 4). Va por el cliente
// pelado: todavía no hay sesión que refrescar.
export function registerOperator({ token, username, password }) {
  return plainClient.post('/auth/register-operator/', { token, username, password })
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

/*
 * El refresh no manda NADA en el cuerpo: el token va en la cookie httpOnly y lo
 * adjunta el navegador. Por eso tampoco hay que preocuparse por qué pestaña tiene
 * el token más nuevo: la cookie es una sola para todo el navegador, así que dos
 * pestañas no pueden quedar desincronizadas como pasaba con localStorage.
 */
function refreshAccessToken() {
  if (!refreshInFlight) {
    refreshInFlight = plainClient
      .post('/auth/refresh/', null, { withCredentials: true })
      .then(({ data }) => {
        useAuthStore.getState().setAccessToken(data.access)
        return data.access
      })
      .finally(() => {
        refreshInFlight = null
      })
  }

  return refreshInFlight
}

/*
 * Al abrir la app: se intenta canjear la cookie por un access token nuevo, para
 * revivir la sesión sin pasar por el login. Si la cookie no está, expiró o el
 * token quedó blacklisteado, el backend responde 401 y la app arranca en el
 * login. (Se intenta solo si hubo una sesión antes en este dispositivo: la
 * cookie es httpOnly, así que desde JS no hay forma de saber si existe.)
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
