import jsQR from 'jsqr'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'

/*
 * Escaneo de código QR en vivo (tarea 11.3). Reutiliza el patrón de cámara de
 * CameraCapture (getUserMedia a pantalla completa), pero en vez de un obturador
 * manual analiza cada frame con jsQR y llama a onDetect apenas decodifica algo.
 *
 * Solo QR: EAN-13/Code128 quedan para el campo de búsqueda manual de
 * NewShipmentPage, que ya acepta el código de barras como texto (es válido para
 * un MVP — ver nota técnica de la tarea).
 *
 * El padre controla qué pasa con cada código detectado (busca el producto,
 * decide si agregarlo) a través de `busy` y `notice`: mientras `busy` es true
 * se deja de decodificar para no disparar el mismo código de nuevo antes de
 * que el padre termine, y `notice` muestra un mensaje corto (ej. "no
 * encontrado") sin cerrar la cámara.
 */
export function BarcodeScanner({ onDetect, onClose, busy = false, notice = null }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const canvasRef = useRef(null)
  const rafRef = useRef(null)
  const lockedRef = useRef(false)
  // Último código ya probado y cuándo: si el código no se encontró, la cámara
  // sigue apuntando al mismo QR en cada frame siguiente, y sin este cooldown
  // se dispara onDetect decenas de veces por segundo (mismo código, mismo 404),
  // lo que además hace parpadear el aviso antes de que el operador llegue a
  // leerlo. Un código DISTINTO no espera el cooldown.
  const lastAttemptRef = useRef({ code: null, at: 0 })
  const RETRY_COOLDOWN_MS = 3000
  const [status, setStatus] = useState('starting') // 'starting' | 'ready' | 'error'
  const [error, setError] = useState(null)

  if (!canvasRef.current) canvasRef.current = document.createElement('canvas')

  // Mientras el padre resuelve la búsqueda (busy), no se decodifica: al volver a
  // false se libera el lock para poder detectar el próximo código.
  useEffect(() => {
    if (!busy) lockedRef.current = false
  }, [busy])

  const tick = useCallback(() => {
    const video = videoRef.current
    if (video?.videoWidth && !lockedRef.current) {
      const canvas = canvasRef.current
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      const ctx = canvas.getContext('2d', { willReadFrequently: true })
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
      const code = jsQR(imageData.data, imageData.width, imageData.height)
      if (code?.data) {
        const last = lastAttemptRef.current
        const sameCodeTooSoon =
          code.data === last.code && Date.now() - last.at < RETRY_COOLDOWN_MS
        if (!sameCodeTooSoon) {
          lastAttemptRef.current = { code: code.data, at: Date.now() }
          lockedRef.current = true
          onDetect(code.data)
        }
      }
    }
    rafRef.current = requestAnimationFrame(tick)
  }, [onDetect])

  useEffect(() => {
    let cancelled = false

    async function start() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('Este navegador no permite usar la cámara. Hace falta una conexión segura (https).')
        setStatus('error')
        return
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: 'environment' },
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
          audio: false,
        })

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
      } catch (caught) {
        if (cancelled) return
        setError(
          caught?.name === 'NotAllowedError'
            ? 'No se pudo acceder a la cámara: falta el permiso del navegador.'
            : 'No se pudo abrir la cámara del dispositivo.',
        )
        setStatus('error')
      }
    }

    start()

    return () => {
      cancelled = true
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
  }, [])

  // El loop de decodificación arranca recién cuando el <video> ya tiene tamaño
  // real (mismo motivo que el obturador de CameraCapture).
  useEffect(() => {
    if (status !== 'ready') return
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [status, tick])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black" data-testid="barcode-scanner">
      <div className="relative min-h-0 w-full flex-1 overflow-hidden">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          onLoadedMetadata={(event) => {
            if (event.currentTarget.videoWidth > 0) setStatus('ready')
          }}
          className="size-full object-contain"
        />

        {status === 'ready' && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-4 p-6">
            {/* Reticle: guía simple para apuntar el código, no hace falta más para el MVP. */}
            <div className="size-56 max-w-full rounded-lg border-2 border-red-500" aria-hidden="true" />
            <p
              role="status"
              data-testid="scanner-hint"
              className="rounded bg-black/60 px-3 py-1 text-center text-sm text-white"
            >
              {busy ? 'Buscando producto…' : 'Apuntá al código'}
            </p>
            {notice && (
              <p
                role="alert"
                data-testid="scanner-notice"
                className="rounded bg-black/60 px-3 py-1 text-center text-sm text-white"
              >
                {notice}
              </p>
            )}
          </div>
        )}

        {status !== 'ready' && (
          <div className="absolute inset-0 flex items-center justify-center p-6 text-center">
            <p role={status === 'error' ? 'alert' : undefined} className="text-sm text-white">
              {status === 'error' ? error : 'Abriendo la cámara…'}
            </p>
          </div>
        )}
      </div>

      <div className="flex shrink-0 items-center justify-center bg-black/80 px-4 pt-4 pb-8">
        <Button
          type="button"
          variant="outline"
          className="h-12 min-w-24"
          onClick={onClose}
          data-testid="scanner-cancel"
        >
          Cancelar
        </Button>
      </div>
    </div>
  )
}
