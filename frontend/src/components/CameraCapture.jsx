import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'

/*
 * Cámara en vivo a pantalla completa (docs/diseno.md sección 5, tarea 2.8).
 *
 * La foto sale SIEMPRE de getUserMedia: en este componente NO hay ningún
 * <input type="file">, así que no se puede adjuntar una imagen de la galería del
 * dispositivo. Es el punto del producto: la evidencia se saca en el momento, no se
 * elige después.
 *
 * onCapture recibe el Blob JPEG del frame; cerrar el overlay lo decide el padre.
 */
export function CameraCapture({ onCapture, onClose }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [status, setStatus] = useState('starting') // 'starting' | 'ready' | 'error'
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function start() {
      // En contextos no seguros (http que no sea localhost) el navegador ni siquiera
      // expone la API: hay que avisarlo, no dejar la pantalla en negro.
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('Este navegador no permite usar la cámara. Hace falta una conexión segura (https).')
        setStatus('error')
        return
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          // Cámara trasera en el celular del operador; en una notebook cae a la única
          // que haya (ideal, no exact, para no fallar si no existe). La resolución
          // también es ideal: si el dispositivo no la tiene, entrega la mayor posible.
          video: {
            facingMode: { ideal: 'environment' },
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
          audio: false,
        })

        // Si el overlay se cerró mientras el usuario decidía el permiso, hay que
        // soltar la cámara igual: si no, queda el led prendido.
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
        // El obturador se habilita recién en onLoadedMetadata: hasta ese momento el
        // <video> puede reportar un tamaño placeholder y la foto saldría en miniatura.
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
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
  }, [])

  const handleCapture = useCallback(() => {
    const video = videoRef.current
    // Sin metadata todavía no hay tamaño real del stream: el canvas saldría vacío.
    if (!video?.videoWidth) return

    // El tamaño lo manda el track, que es la resolución real de la cámara; el
    // <video> es solo el fallback (algunos entornos reportan un tamaño placeholder).
    const settings = streamRef.current?.getVideoTracks()[0]?.getSettings() ?? {}
    const canvas = document.createElement('canvas')
    canvas.width = settings.width || video.videoWidth
    canvas.height = settings.height || video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
    canvas.toBlob((blob) => blob && onCapture(blob), 'image/jpeg', 0.9)
  }, [onCapture])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black" data-testid="camera">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        onLoadedMetadata={(event) => {
          // videoWidth/videoHeight recién son el tamaño real del stream acá.
          if (event.currentTarget.videoWidth > 0) setStatus('ready')
        }}
        className="min-h-0 w-full flex-1 object-contain"
      />

      {status !== 'ready' && (
        <div className="absolute inset-0 flex items-center justify-center p-6 text-center">
          <p role={status === 'error' ? 'alert' : undefined} className="text-sm text-white">
            {status === 'error' ? error : 'Abriendo la cámara…'}
          </p>
        </div>
      )}

      {/* Controles con targets grandes: se usa con una mano y posiblemente con guantes. */}
      <div className="flex shrink-0 items-center justify-between gap-4 bg-black/80 px-4 pt-4 pb-8">
        <Button
          type="button"
          variant="outline"
          className="h-12 min-w-24"
          onClick={onClose}
          data-testid="camera-cancel"
        >
          Cancelar
        </Button>

        <button
          type="button"
          aria-label="Sacar foto"
          data-testid="camera-shutter"
          disabled={status !== 'ready'}
          onClick={handleCapture}
          className="size-20 rounded-full border-4 border-white bg-white/20 disabled:opacity-40"
        />

        {/* Contrapeso del botón "Cancelar" para que el obturador quede centrado. */}
        <span className="h-12 min-w-24" aria-hidden="true" />
      </div>
    </div>
  )
}
