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
 * jsQR se probó corriendo en CADA frame (hasta 60/seg) y se sentía lento: a
 * 1920x1080 el `getImageData` + decode de cada frame es pesado, y correrlo así
 * de seguido satura el hilo principal (la cámara y el resto de la pantalla se
 * ponen a los tirones). Acá se cachea la resolución a 1280x720 —de sobra para
 * un código a la distancia a la que se lo apunta a propósito— y el decode se
 * throttlea a SCAN_INTERVAL_MS: el ojo humano no nota la diferencia entre
 * decodificar 60 o ~8 veces por segundo, pero el hilo principal sí. Adentro de
 * ese mismo intervalo, si jsQR no encontró nada, `Quagga.decodeSingle`
 * relocaliza y decodifica la imagen entera de nuevo —no es un stream continuo
 * como jsQR—, así que además tiene su propio cooldown más largo
 * (QUAGGA_INTERVAL_MS): es la pasada más cara de las dos (recodifica a JPEG)
 * y no hace falta intentarla tan seguido.
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
const SCAN_INTERVAL_MS = 120
const QUAGGA_INTERVAL_MS = 450
const QUAGGA_READERS = ['ean_reader', 'ean_8_reader', 'code_128_reader']

/*
 * Recorte al reticle: sin esto, jsQR/Quagga analizan el FRAME ENTERO, así que
 * cualquier texto o número que quede alrededor del código dentro de cuadro
 * (una etiqueta con tablas, otro código, lo que sea) es candidato a
 * "detectado" tanto como el código real — es lo que reportaba el operador
 * como "el sistema lee cualquier cosa" en una caja con números impresos
 * alrededor del código de barras. La solución no es al revés (ajustar el
 * reticle a lo que se decodifica): es que las dos librerías reciban SOLO los
 * píxeles que caen dentro del reticle.
 *
 * El <video> usa `object-fit: contain`, así que la imagen se ve completa
 * pero con letterbox (barras) si el aspect ratio del contenedor no coincide
 * con el de la cámara — el reticle está posicionado en pantalla relativo al
 * contenedor, no al frame nativo. `computeCropRect` deshace ese letterbox
 * para traducir el rectángulo del reticle (coordenadas de pantalla) a
 * coordenadas de píxel del video nativo, que es lo que hace falta para
 * recortar con `drawImage`.
 */
function computeCropRect(video, reticle) {
  const videoRect = video.getBoundingClientRect()
  const reticleRect = reticle.getBoundingClientRect()
  const videoAspect = video.videoWidth / video.videoHeight
  const boxAspect = videoRect.width / videoRect.height

  let displayWidth
  let displayHeight
  let offsetX
  let offsetY
  if (boxAspect > videoAspect) {
    displayHeight = videoRect.height
    displayWidth = displayHeight * videoAspect
    offsetX = (videoRect.width - displayWidth) / 2
    offsetY = 0
  } else {
    displayWidth = videoRect.width
    displayHeight = displayWidth / videoAspect
    offsetX = 0
    offsetY = (videoRect.height - displayHeight) / 2
  }

  const scale = video.videoWidth / displayWidth
  const x = (reticleRect.left - videoRect.left - offsetX) * scale
  const y = (reticleRect.top - videoRect.top - offsetY) * scale
  const w = reticleRect.width * scale
  const h = reticleRect.height * scale

  // Clamp: si algo dio un valor fuera de rango (redondeos, un layout todavía
  // no asentado), mejor un recorte un poco corrido que un `drawImage` con
  // dimensiones inválidas, que tira excepción y corta el loop de escaneo.
  const clampedX = Math.max(0, Math.min(x, video.videoWidth - 1))
  const clampedY = Math.max(0, Math.min(y, video.videoHeight - 1))
  return {
    x: clampedX,
    y: clampedY,
    w: Math.max(1, Math.min(w, video.videoWidth - clampedX)),
    h: Math.max(1, Math.min(h, video.videoHeight - clampedY)),
  }
}

export function BarcodeScanner({
  onDetect,
  onClose,
  onRetryNotice,
  busy = false,
  notice = null,
  success = false,
}) {
  const videoRef = useRef(null)
  const reticleRef = useRef(null)
  const streamRef = useRef(null)
  const canvasRef = useRef(null)
  const rafRef = useRef(null)
  const cropRectRef = useRef(null)
  const lockedRef = useRef(false)
  // Último código ya probado y cuándo: si el código no se encontró, la cámara
  // sigue apuntando al mismo código en cada frame siguiente, y sin este
  // cooldown se dispara onDetect decenas de veces por segundo (mismo código,
  // mismo 404), lo que además hace parpadear el aviso antes de que el
  // operador llegue a leerlo. Un código DISTINTO no espera el cooldown.
  const lastAttemptRef = useRef({ code: null, at: 0 })
  const lastScanAtRef = useRef(0)
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
    const now = Date.now()
    if (video?.videoWidth && !lockedRef.current && now - lastScanAtRef.current >= SCAN_INTERVAL_MS) {
      lastScanAtRef.current = now
      const canvas = canvasRef.current
      const crop = cropRectRef.current
      const ctx = canvas.getContext('2d', { willReadFrequently: true })
      if (crop) {
        canvas.width = crop.w
        canvas.height = crop.h
        ctx.drawImage(video, crop.x, crop.y, crop.w, crop.h, 0, 0, crop.w, crop.h)
      } else {
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      }
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
      const code = jsQR(imageData.data, imageData.width, imageData.height)
      if (code?.data) {
        reportCode(code.data)
      } else if (quaggaRef.current && !quaggaBusyRef.current) {
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
            width: { ideal: 1280 },
            height: { ideal: 720 },
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

  // El recorte se recalcula cuando la cámara queda lista (recién ahí el
  // reticle y el <video> tienen su tamaño final) y si cambia el layout
  // (rotar el celular, redimensionar la ventana) — la posición en pantalla
  // del reticle relativa al video cambia con eso.
  useEffect(() => {
    if (status !== 'ready') return
    const recompute = () => {
      if (videoRef.current && reticleRef.current) {
        cropRectRef.current = computeCropRect(videoRef.current, reticleRef.current)
      }
    }
    recompute()
    window.addEventListener('resize', recompute)
    window.addEventListener('orientationchange', recompute)
    return () => {
      window.removeEventListener('resize', recompute)
      window.removeEventListener('orientationchange', recompute)
    }
  }, [status])

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
            {/* Reticle: guía simple para apuntar el código, y también el recorte real
                que se decodifica (ver computeCropRect) — todo lo que quede afuera no
                se analiza. */}
            <div
              ref={reticleRef}
              className="size-56 max-w-full rounded-lg border-2 border-red-500"
              aria-hidden="true"
            />

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
