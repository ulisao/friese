import { create } from 'zustand'

/*
 * Estado de auth del operador.
 *
 * El access token vive SOLO en memoria. El refresh token se persiste en
 * localStorage para que la sesión sobreviva a una recarga o al cierre de la
 * pestaña: sin eso, el refresh de 75 días de la sección 4 no serviría de nada
 * (el celular del operador descarta la pestaña en segundo plano todo el tiempo).
 *
 * PROVISORIO: localStorage es legible por JavaScript. La tarea 6.7 mueve el
 * refresh token a una cookie httpOnly, que es la versión definitiva.
 */
const REFRESH_KEY = 'friese.refresh'
const USERNAME_KEY = 'friese.username'

// localStorage puede no existir (SSR, scripts de test) o tirar excepción
// (Safari en modo privado): si falla, la app sigue andando sin persistencia.
function readStored(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStored(key, value) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    /* sin persistencia: la sesión dura lo que dure la pestaña */
  }
}

export function readStoredRefreshToken() {
  return readStored(REFRESH_KEY)
}

const storedRefresh = readStored(REFRESH_KEY)

export const useAuthStore = create((set) => ({
  accessToken: null,
  refreshToken: storedRefresh,
  username: readStored(USERNAME_KEY),

  // 'bootstrapping': hay un refresh guardado y todavía se está intentando
  // revivir la sesión. Hasta que resuelva no se decide login vs. app.
  status: storedRefresh ? 'bootstrapping' : 'anonymous',

  // Arranca la sesión después de un login exitoso.
  setSession: ({ access, refresh, username }) => {
    writeStored(REFRESH_KEY, refresh ?? null)
    writeStored(USERNAME_KEY, username ?? null)
    set({ accessToken: access, refreshToken: refresh, username, status: 'authenticated' })
  },

  // Guarda el par de tokens que devuelve /api/auth/refresh/. El refresh también
  // cambia porque el backend rota (ROTATE_REFRESH_TOKENS) y blacklistea el viejo.
  setTokens: ({ access, refresh }) =>
    set((state) => {
      const nextRefresh = refresh ?? state.refreshToken
      writeStored(REFRESH_KEY, nextRefresh ?? null)
      return { accessToken: access, refreshToken: nextRefresh, status: 'authenticated' }
    }),

  // Cierra la sesión: las rutas protegidas mandan al login al quedar sin token.
  clearSession: () => {
    writeStored(REFRESH_KEY, null)
    writeStored(USERNAME_KEY, null)
    set({ accessToken: null, refreshToken: null, username: null, status: 'anonymous' })
  },
}))

export const isAuthenticated = (state) => state.status === 'authenticated'
export const isBootstrapping = (state) => state.status === 'bootstrapping'
