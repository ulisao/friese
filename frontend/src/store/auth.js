import { create } from 'zustand'

/*
 * Estado de auth del operador.
 *
 * El access token vive SOLO en memoria. El refresh token ya no está acá ni en
 * localStorage: desde la tarea 6.7 vive en una cookie httpOnly que pone el
 * backend, o sea que JavaScript no puede leerlo (ante un XSS no hay nada que
 * robar) y el navegador la manda solo a /api/auth/.
 *
 * Lo único que se persiste es el NOMBRE de usuario, que no es una credencial:
 * sirve para saber, al abrir la app, si vale la pena intentar revivir la sesión
 * (la cookie no se puede consultar desde JS) y para mostrarlo en la pantalla.
 */
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

const storedUsername = readStored(USERNAME_KEY)

export const useAuthStore = create((set) => ({
  accessToken: null,
  username: storedUsername,

  // 'bootstrapping': hubo una sesión en este dispositivo y todavía se está
  // intentando revivirla con la cookie. Hasta que resuelva no se decide login
  // vs. app.
  status: storedUsername ? 'bootstrapping' : 'anonymous',

  // Arranca la sesión después de un login exitoso. El refresh NO viene acá: se
  // lo quedó el navegador en la cookie httpOnly.
  setSession: ({ access, username }) => {
    writeStored(USERNAME_KEY, username ?? null)
    set({ accessToken: access, username, status: 'authenticated' })
  },

  // Guarda el access nuevo que devolvió /api/auth/refresh/. El refresh rotado
  // viaja en la cookie de la respuesta, no por acá.
  setAccessToken: (access) => set({ accessToken: access, status: 'authenticated' }),

  // Cierra la sesión: las rutas protegidas mandan al login al quedar sin token.
  clearSession: () => {
    writeStored(USERNAME_KEY, null)
    set({ accessToken: null, username: null, status: 'anonymous' })
  },
}))

export const isAuthenticated = (state) => state.status === 'authenticated'
export const isBootstrapping = (state) => state.status === 'bootstrapping'
