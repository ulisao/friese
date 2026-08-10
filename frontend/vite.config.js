import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import basicSsl from '@vitejs/plugin-basic-ssl'

/*
 * DEV_HTTPS=1 sirve el dev server por https con un certificado autofirmado.
 * Hace falta SOLO para probar desde el celular por la red local: la cámara
 * (getUserMedia) únicamente funciona en contexto seguro, o sea https o localhost.
 * En el desarrollo normal en la máquina no se usa (http://localhost alcanza).
 */
const useHttps = Boolean(process.env.DEV_HTTPS)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), ...(useHttps ? [basicSsl()] : [])],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    /*
     * La API se consume por el MISMO origen que el frontend (/api → Django). Así,
     * al entrar desde el celular por https, las llamadas no quedan como contenido
     * mixto (https → http) ni pasan por CORS. changeOrigin manda el Host del
     * destino, que es el que Django tiene en ALLOWED_HOSTS.
     */
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
