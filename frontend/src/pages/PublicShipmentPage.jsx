import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { CameraCapture } from '@/components/CameraCapture'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { publicApi } from '@/lib/api'

const dateFormatter = new Intl.DateTimeFormat('es-AR', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : dateFormatter.format(date)
}

/*
 * Pantalla ÚNICA del receptor (tarea 3.4), pública y sin login: es lo que se abre
 * desde el link {FRONTEND_PUBLIC_URL}/remito/{public_token} que le llega por email.
 *
 * Layout centrado a una columna y fotos grandes (docs/diseno.md sección 5). Los dos
 * CTA usan los colores fijos de estado: conforme = green-500 (accepted), reportar un
 * problema = red-500 (disputed).
 *
 * El flujo entero vive acá:
 *  - carga el remito con GET /api/public/shipment/{token}/ (eso sella la ventana de 48hs),
 *  - si todavía admite respuesta, muestra los dos botones,
 *  - "Reportar un problema" abre la cámara en vivo (sin galería) y un texto opcional,
 *  - si el remito ya fue respondido (o se cerró solo), muestra únicamente el resultado.
 *
 * El receptor no es un usuario técnico: ningún mensaje de error muestra códigos ni
 * estados crudos de la API; se traducen todos a castellano llano.
 */
export function PublicShipmentPage() {
  const { token } = useParams()

  const [shipment, setShipment] = useState(null)
  const [status, setStatus] = useState('loading') // 'loading' | 'ready' | 'notfound' | 'error'

  // Fotos sacadas por el receptor que todavía no confirmó el backend.
  // { key, previewUrl, blob, itemId, state: 'uploading' | 'error' }
  const [pending, setPending] = useState([])
  const pendingRef = useRef(pending)
  pendingRef.current = pending

  const [reporting, setReporting] = useState(false) // panel de "Reportar un problema"
  const [reason, setReason] = useState('')
  const [cameraItemId, setCameraItemId] = useState(null) // null = foto del remito completo
  const [cameraOpen, setCameraOpen] = useState(false)
  const [confirmAcceptOpen, setConfirmAcceptOpen] = useState(false)
  const [submitting, setSubmitting] = useState(null) // 'accept' | 'dispute' | null
  const [actionError, setActionError] = useState(null)

  const load = useCallback(async () => {
    setStatus('loading')
    try {
      const { data } = await publicApi.get(`/public/shipment/${token}/`)
      setShipment(data)
      setStatus('ready')
    } catch (error) {
      // 404 = el token no existe (link incompleto, mal copiado o remito borrado).
      // Cualquier otra cosa es un problema de conexión o del servidor: se reintenta.
      setStatus(error?.response?.status === 404 ? 'notfound' : 'error')
    }
  }, [token])

  useEffect(() => {
    load()
  }, [load])

  // Las previews son object URLs: si no se liberan al salir, el blob de cada foto
  // queda retenido en memoria.
  useEffect(() => {
    return () => {
      pendingRef.current.forEach((photo) => URL.revokeObjectURL(photo.previewUrl))
    }
  }, [])

  const uploadPhoto = useCallback(
    async (photo) => {
      setPending((current) =>
        current.map((item) => (item.key === photo.key ? { ...item, state: 'uploading' } : item)),
      )

      const form = new FormData()
      // El backend arma el nombre real del objeto en R2 con un uuid; de este nombre
      // solo usa la extensión.
      form.append('file', photo.blob, 'recepcion.jpg')
      // Sin ítem la foto documenta la carga completa (el backend lo deja en null).
      if (photo.itemId != null) form.append('shipment_item', photo.itemId)

      try {
        const { data } = await publicApi.post(`/public/shipment/${token}/evidence/`, form)
        // Confirmada por el backend: pasa a la lista real del remito y deja de estar
        // pendiente. La preview local ya no hace falta.
        setShipment((current) =>
          current
            ? { ...current, reception_evidence: [...(current.reception_evidence ?? []), data] }
            : current,
        )
        setPending((current) => current.filter((item) => item.key !== photo.key))
        URL.revokeObjectURL(photo.previewUrl)
      } catch {
        // El blob se conserva para poder reintentar sin volver a sacar la foto.
        setPending((current) =>
          current.map((item) => (item.key === photo.key ? { ...item, state: 'error' } : item)),
        )
      }
    },
    [token],
  )

  const handleCapture = useCallback(
    (blob) => {
      const photo = {
        key: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        previewUrl: URL.createObjectURL(blob),
        blob,
        itemId: cameraItemId,
        state: 'uploading',
      }
      setCameraOpen(false)
      setPending((current) => [...current, photo])
      uploadPhoto(photo)
    },
    [cameraItemId, uploadPhoto],
  )

  function openCamera(itemId) {
    setCameraItemId(itemId)
    setCameraOpen(true)
  }

  function handleDiscard(photo) {
    setPending((current) => current.filter((item) => item.key !== photo.key))
    URL.revokeObjectURL(photo.previewUrl)
  }

  /*
   * Registra la respuesta (conformidad o queja). El backend contesta 400 con un
   * mensaje que nombra estados internos ('accepted', 'dispatched'): eso no se le
   * muestra al receptor. Se traduce a una frase llana y se recarga el remito, así la
   * pantalla pasa sola al modo resultado con el estado real.
   */
  async function respond(kind) {
    setSubmitting(kind)
    setActionError(null)
    try {
      const { data } =
        kind === 'accept'
          ? await publicApi.post(`/public/shipment/${token}/accept/`)
          : await publicApi.post(`/public/shipment/${token}/dispute/`, {
              dispute_reason: reason.trim(),
            })
      setShipment(data)
      setConfirmAcceptOpen(false)
      setReporting(false)
    } catch (error) {
      if (error?.response?.status === 400) {
        setActionError(
          'Este remito ya no admite respuesta: o alguien ya respondió, o pasaron las 48 horas.',
        )
        setConfirmAcceptOpen(false)
        load()
      } else {
        setActionError('No pudimos registrar tu respuesta. Revisá tu conexión e intentá de nuevo.')
      }
    } finally {
      setSubmitting(null)
    }
  }

  if (status === 'loading') {
    return (
      <main className="flex min-h-svh items-center justify-center p-4">
        <p className="text-sm text-muted-foreground">Cargando el remito…</p>
      </main>
    )
  }

  if (status === 'notfound' || status === 'error') {
    const isNotFound = status === 'notfound'
    return (
      <main className="mx-auto flex min-h-svh w-full max-w-md flex-col items-center justify-center gap-4 p-6 text-center">
        <h1 className="text-xl font-semibold">
          {isNotFound ? 'No encontramos este remito' : 'No pudimos abrir el remito'}
        </h1>
        <p role="alert" className="text-sm text-muted-foreground" data-testid="load-error">
          {isNotFound
            ? 'El link puede estar incompleto o cortado. Abrilo de nuevo desde el email que recibiste, o pedile a quien te lo mandó que te lo reenvíe.'
            : 'Revisá tu conexión a internet e intentá de nuevo.'}
        </p>
        {!isNotFound && (
          <Button type="button" className="h-12 w-full" onClick={load}>
            Reintentar
          </Button>
        )}
      </main>
    )
  }

  const items = shipment.items ?? []
  const dispatchPhotos = shipment.evidence ?? []
  const receptionPhotos = shipment.reception_evidence ?? []
  // Nombre del producto de cada foto: la evidencia trae el id del ítem, no el nombre.
  const itemNames = new Map(items.map((item) => [item.id, item.product_name]))
  const photoLabel = (itemId) =>
    itemId == null ? 'Carga completa' : (itemNames.get(itemId) ?? 'Producto eliminado')
  const countFor = (itemId) =>
    receptionPhotos.filter((photo) => photo.shipment_item === itemId).length +
    pending.filter((photo) => photo.itemId === itemId).length

  // La ventana pudo vencer sin que la tarea periódica (3.3) haya pasado todavía: el
  // remito sigue figurando despachado pero el backend ya no acepta la respuesta. Se
  // chequea acá para no ofrecer botones que van a fallar.
  const deadline = shipment.response_deadline ? new Date(shipment.response_deadline) : null
  const deadlinePassed = deadline != null && !Number.isNaN(deadline.getTime()) && deadline < new Date()
  const canRespond = shipment.status === 'dispatched' && !deadlinePassed

  // Sin foto el backend no registra la queja (sección 5: "registra queja con foto").
  const hasUploadedPhoto = receptionPhotos.length > 0
  const hasUnconfirmedPhotos = pending.length > 0

  function finalMessage() {
    if (shipment.status === 'accepted') {
      return shipment.auto_closed
        ? 'Pasaron las 48 horas sin respuesta, así que el remito se cerró solo y quedó registrado como recibido conforme.'
        : 'Confirmaste la recepción: el remito quedó registrado como recibido conforme.'
    }
    if (shipment.status === 'disputed') {
      return `Reportaste un problema con esta entrega. ${shipment.company_name} ya tiene tu reporte y las fotos que sacaste.`
    }
    if (shipment.status === 'closed') {
      return 'Este remito está cerrado y ya no admite respuestas.'
    }
    // dispatched con la ventana vencida (todavía sin cerrar por la tarea periódica).
    return `El plazo de 48 horas para responder venció el ${formatDate(shipment.response_deadline)} — si tenés algo que reclamar, comunicate directamente con ${shipment.company_name}.`
  }

  return (
    <div className="min-h-svh">
      {/* Una sola columna, centrada (docs/diseno.md sección 5, frontend receptor). */}
      <main className="mx-auto flex w-full max-w-md flex-col gap-4 px-4 pt-6 pb-10">
        <header className="flex flex-col items-center gap-2 text-center">
          <p className="text-sm text-muted-foreground">{shipment.company_name}</p>
          <h1 className="text-2xl font-semibold">Remito #{shipment.id}</h1>
          <p className="text-sm text-muted-foreground">Para {shipment.receiver_name}</p>
          <StatusBadge status={shipment.status} />
        </header>

        {canRespond ? (
          <p className="rounded-md border p-3 text-center text-sm text-muted-foreground">
            Revisá los productos y las fotos del despacho, y confirmá si recibiste todo bien.
            {/* El formato es-AR ya termina en punto ("09:53 a. m."): la frase se arma
                para que la fecha no quede al final y no se vea un punto doble. */}
            {deadline && ` Tenés tiempo hasta el ${formatDate(shipment.response_deadline)} para responder.`}
          </p>
        ) : (
          <p
            role="status"
            data-testid="final-message"
            className="rounded-md border p-3 text-center text-sm"
          >
            {finalMessage()}
          </p>
        )}

        <Card className="gap-4 rounded-lg p-4">
          <CardHeader className="p-0">
            <CardTitle className="text-base">Productos</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {items.length === 0 ? (
              <p className="text-sm text-muted-foreground">Este remito no detalla productos.</p>
            ) : (
              <ul className="flex flex-col gap-2" data-testid="shipment-items">
                {items.map((item) => (
                  <li key={item.id} className="rounded-md border p-3" data-item-id={item.id}>
                    <p className="font-medium">{item.product_name}</p>
                    {/* La unidad va SIEMPRE junto a la cantidad (ej. "50 bolsas"). */}
                    <p className="text-sm text-muted-foreground">
                      {Number(item.quantity)} {item.product_unit}
                    </p>
                    {item.notes && <p className="text-sm text-muted-foreground">{item.notes}</p>}

                    {reporting && (
                      <>
                        <p
                          className="pt-1 text-xs text-muted-foreground"
                          data-item-photos={countFor(item.id)}
                        >
                          {countFor(item.id) === 0
                            ? 'Sin fotos de este producto'
                            : `${countFor(item.id)} foto${countFor(item.id) === 1 ? '' : 's'} de este producto`}
                        </p>
                        <Button
                          type="button"
                          variant="outline"
                          className="mt-2 h-12 w-full"
                          data-testid={`open-camera-item-${item.id}`}
                          onClick={() => openCamera(item.id)}
                        >
                          Sacar foto de este producto
                        </Button>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="gap-4 rounded-lg p-4">
          <CardHeader className="p-0">
            <CardTitle className="text-base">Fotos del despacho</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 p-0">
            {dispatchPhotos.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Este remito se despachó sin fotos de evidencia.
              </p>
            ) : (
              /* Fotos grandes, una por fila: es lo que el receptor tiene que mirar
                 para decidir (docs/diseno.md sección 5). */
              <ul className="flex flex-col gap-4" data-testid="dispatch-evidence">
                {dispatchPhotos.map((photo) => (
                  <li key={photo.id} data-evidence-id={photo.id}>
                    <img
                      src={photo.file_url}
                      alt={`Foto del despacho del remito #${shipment.id}`}
                      className="w-full rounded-md border object-contain"
                    />
                    <p className="pt-1 text-xs font-medium">{photoLabel(photo.shipment_item)}</p>
                    <p className="text-xs text-muted-foreground">
                      Sacada el {formatDate(photo.uploaded_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Panel de la queja: solo se abre con "Reportar un problema". */}
        {reporting && (
          <Card className="gap-4 rounded-lg p-4" data-testid="dispute-panel">
            <CardHeader className="p-0">
              <CardTitle className="text-base">Fotos de lo que recibiste</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 p-0">
              <p className="text-sm text-muted-foreground">
                Sacá al menos una foto de la carga como llegó. Podés sacar varias, y también
                una por producto desde la lista de arriba.
              </p>

              {(receptionPhotos.length > 0 || pending.length > 0) && (
                <ul className="grid grid-cols-2 gap-3" data-testid="reception-evidence">
                  {receptionPhotos.map((photo) => (
                    <li key={`reception-${photo.id}`} data-reception-id={photo.id}>
                      <img
                        src={photo.file_url}
                        alt="Foto de la carga recibida"
                        className="aspect-square w-full rounded-md border object-cover"
                      />
                      <p className="truncate pt-1 text-xs font-medium">
                        {photoLabel(photo.shipment_item)}
                      </p>
                    </li>
                  ))}

                  {pending.map((photo) => (
                    <li key={photo.key} data-pending-state={photo.state}>
                      <img
                        src={photo.previewUrl}
                        alt="Foto pendiente de subir"
                        className="aspect-square w-full rounded-md border object-cover opacity-60"
                      />
                      <p className="truncate pt-1 text-xs font-medium">
                        {photoLabel(photo.itemId)}
                      </p>
                      {photo.state === 'uploading' ? (
                        <p className="pt-1 text-xs text-muted-foreground">Subiendo…</p>
                      ) : (
                        <div className="flex flex-col gap-2 pt-1">
                          <p role="alert" className="text-xs text-destructive">
                            No se pudo subir.
                          </p>
                          <Button type="button" className="h-12" onClick={() => uploadPhoto(photo)}>
                            Reintentar
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            className="h-12"
                            onClick={() => handleDiscard(photo)}
                          >
                            Descartar
                          </Button>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}

              {/* Sin input de archivo: la foto sale siempre de la cámara en vivo. */}
              <Button
                type="button"
                variant="outline"
                className="h-12 w-full"
                data-testid="open-camera"
                onClick={() => openCamera(null)}
              >
                Sacar foto de la carga
              </Button>

              <div className="flex flex-col gap-2">
                <label htmlFor="dispute-reason" className="text-sm font-medium">
                  ¿Qué pasó? (opcional)
                </label>
                <Textarea
                  id="dispute-reason"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="Ej.: llegaron 45 bolsas en vez de 50, y 3 estaban rotas."
                  className="min-h-24"
                />
              </div>

              {!hasUploadedPhoto && (
                <p className="text-sm text-muted-foreground">
                  Para enviar el reporte hace falta al menos una foto.
                </p>
              )}
              {hasUnconfirmedPhotos && (
                <p className="text-sm text-muted-foreground">
                  Esperá a que terminen de subirse las fotos.
                </p>
              )}

              <Button
                type="button"
                data-testid="dispute-confirm"
                disabled={!hasUploadedPhoto || hasUnconfirmedPhotos || submitting !== null}
                className="h-14 w-full bg-red-500 text-base font-semibold text-white hover:bg-red-500/90"
                onClick={() => respond('dispute')}
              >
                {submitting === 'dispute' ? 'Enviando…' : 'Enviar el reporte'}
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-12 w-full"
                disabled={submitting !== null}
                onClick={() => {
                  setReporting(false)
                  setActionError(null)
                }}
              >
                Cancelar
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Las fotos y el motivo quedan a la vista después de reportar el problema. */}
        {!canRespond && shipment.status === 'disputed' && (
          <Card className="gap-4 rounded-lg p-4">
            <CardHeader className="p-0">
              <CardTitle className="text-base">Tu reporte</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 p-0">
              {shipment.dispute_reason && (
                <p className="text-sm" data-testid="dispute-reason">
                  {shipment.dispute_reason}
                </p>
              )}
              {receptionPhotos.length > 0 && (
                <ul className="grid grid-cols-2 gap-3" data-testid="reception-evidence">
                  {receptionPhotos.map((photo) => (
                    <li key={`reception-${photo.id}`} data-reception-id={photo.id}>
                      <img
                        src={photo.file_url}
                        alt="Foto de la carga recibida"
                        className="aspect-square w-full rounded-md border object-cover"
                      />
                      <p className="truncate pt-1 text-xs font-medium">
                        {photoLabel(photo.shipment_item)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        )}

        {actionError && (
          <p role="alert" className="text-sm text-destructive" data-testid="action-error">
            {actionError}
          </p>
        )}

        {/* Los dos CTA, diferenciados por el color de estado: verde = accepted,
            rojo = disputed (docs/diseno.md secciones 2 y 5). */}
        {canRespond && !reporting && (
          <div className="flex flex-col gap-3">
            <Button
              type="button"
              data-testid="accept"
              disabled={submitting !== null}
              className="h-14 w-full bg-green-500 text-base font-semibold text-background hover:bg-green-500/90"
              onClick={() => {
                setActionError(null)
                setConfirmAcceptOpen(true)
              }}
            >
              Conforme
            </Button>
            <Button
              type="button"
              data-testid="report"
              disabled={submitting !== null}
              className="h-14 w-full bg-red-500 text-base font-semibold text-white hover:bg-red-500/90"
              onClick={() => {
                setActionError(null)
                setReporting(true)
              }}
            >
              Reportar un problema
            </Button>
          </div>
        )}
      </main>

      {cameraOpen && (
        <CameraCapture onCapture={handleCapture} onClose={() => setCameraOpen(false)} />
      )}

      {/* Dar conformidad es irreversible: un solo toque no puede cerrarlo. */}
      <Dialog
        open={confirmAcceptOpen}
        onOpenChange={(open) => submitting === null && setConfirmAcceptOpen(open)}
      >
        <DialogContent data-testid="accept-dialog">
          <DialogHeader>
            <DialogTitle>¿Recibiste todo conforme?</DialogTitle>
            <DialogDescription>
              Queda registrado que recibiste la carga sin problemas. Después de confirmar no vas
              a poder reportar un problema por este remito.
            </DialogDescription>
          </DialogHeader>

          {actionError && (
            <p role="alert" className="text-sm text-destructive">
              {actionError}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              className="h-12"
              disabled={submitting !== null}
              onClick={() => setConfirmAcceptOpen(false)}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              data-testid="accept-confirm"
              disabled={submitting !== null}
              className="h-12 bg-green-500 font-semibold text-background hover:bg-green-500/90"
              onClick={() => respond('accept')}
            >
              {submitting === 'accept' ? 'Confirmando…' : 'Sí, está todo bien'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
