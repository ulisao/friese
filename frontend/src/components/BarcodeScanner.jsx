import jsQR from 'jsqr'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'

/*
 * Escaneo de código en vivo (tarea 11.3, ampliado en la 11.4). Reutiliza el
 * patrón de cámara de CameraCapture (getUserMedia a pantalla completa), pero
 * en vez de un obturador manual analiza cada frame con jsQR y llama a
 * onDetect apenas decodifica algo.
 *
 * Tarea 11.4 — nota sobre libraries y dependencias, opción B: además de QR
 * (jsQR, ~5KB, va en el bundle principal) ahora también decodifica
 * EAN-13/EAN-8/Code128 con `@ericblade/quagga2`, pero ESE paquete se
 * `import()` dinámico recién al montar este componente (es decir, cuando el
 * operador aprieta "Escanear"), nunca en la carga inicial de la app — si la
 * descarga falla (offline, bloqueado) no es fatal, se sigue escaneando QR
 * igual. `quagga2` declara `sharp`/`ndarray-pixels` como
 * optionalDependencies para su modo Node (decodificar un archivo en disco);
 * el build de Vite usa el campo "browser" del paquete (`dist/quagga.min.js`)
 * y nunca los importa, así que no viajan al bundle ni corren en el navegador.
 *
 * jsQR corre en CADA frame (muy liviano, es lo común: QR). `Quagga.decodeSingle`
 * relocaliza y decodifica la imagen entera cada vez que se llama —no es un
 * stream continuo como jsQR—, así que se llama cada QUAGGA_INTERVAL_MS sobre
 * el mismo canvas ya capturado, y solo cuando jsQR no encontró nada en ese
 * frame. Tirarlo en cada frame saturaría la CPU del celular sin ganar nada.
 *
 * El padre controla qué pasa con cada código detectado (busca el producto,
 * decide si agregarlo) a través de `busy`, `notice` y `success`: mientras
 * `busy` es true se deja de decodificar para no disparar el mismo código de
 * nuevo antes de que el padre termine, `notice` muestra un mensaje corto de
 * error (ej. "no encontrado") con opción de reintentar o pasar a carga
 * manual, y `success` muestra brevemente una confirmación antes de que el
 * padre cierre la cámara.
 */
const RETRY_COOLDOWN_MS = 3000
const QUAGGA_INTERVAL_MS = 450
const QUAGGA_READERS = ['ean_reader', 'ean_8_reader', 'code_128_reader']

export function BarcodeScanner({
  onDetect,
  onClose,
  onRetryNotice,
  busy = false,
  notice = null,
  success = false,
}) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const canvasRef = useRef(null)
  const rafRef = useRef(null)
  const lockedRef = useRef(false)
  // Último código ya probado y cuándo: si el código no se encontró, la cámara
  // sigue apuntando al mismo código en cada frame siguiente, y sin este
  // cooldown se dispara onDetect decenas de veces por segundo (mismo código,
  // mismo 404), lo que además hace parpadear el aviso antes de que el
  // operador llegue a leerlo. Un código DISTINTO no espera el cooldown.
  const lastAttemptRef = useRef({ code: null, at: 0 })
  const quaggaRef = useRef(null)
  const quaggaBusyRef = useRef(false)
  const lastQuaggaAttemptRef = useRef(0)
  const [status, setStatus] = useState('starting') // 'starting' | 'ready' | 'error'
  const [error, setError] = useState(null)

  if (!canvasRef.current) canvasRef.current = document.createElement('canvas')

  // Mientras el padre resuelve la búsqueda (busy), no se decodifica: al volver a
  // false se libera el lock para poder detectar el próximo código.
  useEffect(() => {
    if (!busy) lockedRef.current = false
  }, [busy])

  useEffect(() => {
    let cancelled = false
    import('@ericblade/quagga2')
      .then((module) => {
        if (!cancelled) quaggaRef.current = module.default ?? module
      })
      .catch(() => {
        // Sin conexión o bloqueado: seguimos solo con QR, no hace falta avisar.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const reportCode = useCallback(
    (value) => {
      const last = lastAttemptRef.current
      const sameCodeTooSoon = value === last.code && Date.now() - last.at < RETRY_COOLDOWN_MS
      if (sameCodeTooSoon) return
      lastAttemptRef.current = { code: value, at: Date.now() }
      lockedRef.current = true
      onDetect(value)
    },
    [onDetect],
  )

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
        reportCode(code.data)
      } else if (quaggaRef.current && !quaggaBusyRef.current) {
        const now = Date.now()
        if (now - lastQuaggaAttemptRef.current >= QUAGGA_INTERVAL_MS) {
          lastQuaggaAttemptRef.current = now
          quaggaBusyRef.current = true
          quaggaRef.current
            .decodeSingle({
              src: canvas.toDataURL('image/jpeg', 0.8),
              numOfWorkers: 0,
              locate: true,
              decoder: { readers: QUAGGA_READERS },
            })
            .then((result) => {
              const barcode = result?.codeResult?.code
              if (barcode) reportCode(barcode)
            })
            .catch(() => {})
            .finally(() => {
              quaggaBusyRef.current = false
            })
        }
      }
    }
    rafRef.current = requestAnimationFrame(tick)
  }, [reportCode])

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

  // Con notice o success mostramos ESO en vez del hint de "apuntá al código":
  // mezclar los tres a la vez recargaba la pantalla justo cuando el operador
  // más necesita leer un solo mensaje claro.
  const showHint = status === 'ready' && !notice && !success

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

            {showHint && (
              <p
                role="status"
                data-testid="scanner-hint"
                className="flex items-center gap-2 rounded bg-black/60 px-3 py-1 text-center text-sm text-white"
              >
                <Loader2
                  className={`size-4 shrink-0 animate-spin ${busy ? '' : 'text-white/50'}`}
                  aria-hidden="true"
                />
                {busy ? 'Buscando producto…' : 'Apuntá al código'}
              </p>
            )}

            {success && (
              <div
                role="status"
                data-testid="scanner-success"
                className="animate-scan-success flex flex-col items-center gap-2 rounded bg-black/70 px-4 py-3 text-white"
              >
                <CheckCircle2 className="size-10 text-green-400" aria-hidden="true" />
                <span className="text-sm">Producto encontrado</span>
              </div>
            )}

            {notice && !success && (
              <div
                className="pointer-events-auto flex flex-col items-center gap-3 rounded bg-black/70 px-4 py-3"
                data-testid="scanner-notice"
              >
                <p role="alert" className="text-center text-sm font-medium text-red-400">
                  {notice}
                </p>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-10"
                    data-testid="scanner-retry"
                    onClick={onRetryNotice}
                  >
                    Intentar de nuevo
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-10"
                    data-testid="scanner-manual"
                    onClick={onClose}
                  >
                    Escribir a mano
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {status !== 'ready' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
            {status === 'starting' && (
              <Loader2 className="size-8 animate-spin text-white/70" aria-hidden="true" />
            )}
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
