import { useEffect } from 'react'

/*
 * Título de la pestaña, por pantalla (tarea 10.5).
 *
 * `index.html` trae un único <title>Friese</title>, así que todas las pantallas se
 * veían igual en la barra de pestañas y en el historial del navegador. Este hook lo
 * escribe al montar cada pantalla y lo devuelve a "Friese" al salir.
 *
 * El separador es "·" y la marca va SIEMPRE al final: en una pestaña angosta —que es
 * como se ve en el celular del operador— lo primero que se corta es lo de la derecha,
 * y lo que tiene que sobrevivir es en qué pantalla está.
 */
const MARCA = 'Friese'

export function useDocumentTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · ${MARCA}` : MARCA
    return () => {
      document.title = MARCA
    }
  }, [title])
}
