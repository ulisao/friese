import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

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
import { api } from '@/lib/api'

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
 * Detalle del remito (tarea 2.8).
 *
 * En draft es operable: sacar fotos de evidencia con la cámara en vivo y despachar.
 * En cualquier otro estado (dispatched/accepted/disputed/closed) es SOLO LECTURA:
 * el despacho es irreversible y el remito queda inmutable (sección 6), así que no
 * se muestra ni la cámara ni el botón de despachar.
 *
 * Orden del flujo: primero las fotos, y recién cuando subieron bien se habilita el
 * despacho. Así un remito nunca queda despachado (irreversible) sin su evidencia; si
 * una subida falla, el remito sigue en draft y el operador reintenta.
 *
 * Cada foto puede ir atada a un producto del remito (botón "Sacar foto" de cada ítem,
 * sin límite de fotos por producto) o al remito completo (botón general). El backend
 * lo guarda en Evidence.shipment_item.
 */
export function ShipmentDetailPage() {
  const { id } = useParams()

  const [shipment, setShipment] = useState(null)
  const [status, setStatus] = useState('loading') // 'loading' | 'ready' | 'error'

  // Fotos sacadas que todavía no están confirmadas por el backend.
  // { key, previewUrl, blob, itemId, state: 'uploading' | 'error' }
  const [pending, setPending] = useState([])
  const pendingRef = useRef(pending)
  pendingRef.current = pending

  // itemId de la foto que se está por sacar: null = foto del remito completo.
  const [cameraItemId, setCameraItemId] = useState(null)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [dispatching, setDispatching] = useState(false)
  const [dispatchError, setDispatchError] = useState(null)

  const load = useCallback(async () => {
    setStatus('loading')
    try {
      const { data } = await api.get(`/shipments/${id}/`)
      setShipment(data)
      setStatus('ready')
    } catch {
      setStatus('error')
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  // Las previews son object URLs: si no se liberan al salir de la pantalla, el blob
  // de cada foto queda retenido en memoria.
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
      form.append('file', photo.blob, 'evidencia.jpg')
      form.append('type', 'dispatch')
      // Sin ítem la foto documenta el remito completo (el backend lo deja en null).
      if (photo.itemId != null) form.append('shipment_item', photo.itemId)

      try {
        const { data } = await api.post(`/shipments/${id}/evidence/`, form)
        // Confirmada por el backend: pasa a la lista real del remito y deja de estar
        // pendiente. La preview local ya no hace falta.
        setShipment((current) =>
          current ? { ...current, evidence: [...(current.evidence ?? []), data] } : current,
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
    [id],
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

  async function handleDispatch() {
    setDispatching(true)
    setDispatchError(null)
    try {
      const { data } = await api.patch(`/shipments/${id}/dispatch/`)
      setShipment(data)
      setConfirmOpen(false)
    } catch (error) {
      const detail = error?.response?.data?.detail
      setDispatchError(
        typeof detail === 'string' ? detail : 'No se pudo despachar el remito. Intentá de nuevo.',
      )
    } finally {
      setDispatching(false)
    }
  }

  if (status === 'loading') {
    return (
      <main className="flex min-h-svh items-center justify-center p-4">
        <p className="text-sm text-muted-foreground">Cargando…</p>
      </main>
    )
  }

  if (status === 'error') {
    return (
      <main className="mx-auto flex min-h-svh w-full max-w-2xl flex-col items-start gap-3 p-4">
        <p role="alert" className="text-sm text-destructive">
          No se pudo cargar el remito.
        </p>
        <div className="flex gap-2">
          <Button variant="outline" className="h-12" onClick={load}>
            Reintentar
          </Button>
          <Button asChild variant="outline" className="h-12">
            <Link to="/">Volver</Link>
          </Button>
        </div>
      </main>
    )
  }

  const isDraft = shipment.status === 'draft'
  const evidence = shipment.evidence ?? []
  const items = shipment.items ?? []
  // Nombre del producto de cada foto: la evidencia trae el id del ítem, no el nombre.
  const itemNames = new Map(items.map((item) => [item.id, item.product_name]))
  const photoLabel = (itemId) =>
    itemId == null ? 'Remito completo' : (itemNames.get(itemId) ?? 'Producto eliminado')
  const countFor = (itemId) =>
    evidence.filter((photo) => photo.shipment_item === itemId).length +
    pending.filter((photo) => photo.itemId === itemId).length
  // Mientras haya fotos sin confirmar (subiendo o falladas) no se despacha: el
  // despacho es irreversible y tiene que salir con la evidencia ya guardada.
  const hasUnconfirmedPhotos = pending.length > 0

  return (
    <div className="min-h-svh">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-2xl items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold">Remito #{shipment.id}</h1>
            <p className="truncate text-sm text-muted-foreground">{shipment.receiver_name}</p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <StatusBadge status={shipment.status} />
            <Button asChild variant="outline" className="h-12">
              <Link to="/">Volver</Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-4 pt-4 pb-8">
        {!isDraft && (
          <p className="rounded-md border p-3 text-sm text-muted-foreground" role="status">
            Este remito ya fue despachado: es inmutable y se muestra en modo lectura.
          </p>
        )}

        <Card className="gap-4 rounded-lg p-4">
          <CardHeader className="p-0">
            <CardTitle className="text-base">Receptor</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-1 p-0 text-sm">
            <p className="font-medium">{shipment.receiver_name}</p>
            {shipment.receiver_email && (
              <p className="text-muted-foreground">{shipment.receiver_email}</p>
            )}
            {shipment.receiver_phone && (
              <p className="text-muted-foreground">{shipment.receiver_phone}</p>
            )}
            <p className="pt-2 text-muted-foreground">Creado el {formatDate(shipment.created_at)}</p>
            {shipment.dispatched_at && (
              <p className="text-muted-foreground">
                Despachado el {formatDate(shipment.dispatched_at)}
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="gap-4 rounded-lg p-4">
          <CardHeader className="p-0">
            <CardTitle className="text-base">Productos</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {items.length === 0 ? (
              <p className="text-sm text-muted-foreground">Este remito no tiene productos.</p>
            ) : (
              <ul className="flex flex-col gap-2" data-testid="shipment-items">
                {items.map((item) => {
                  const photos = countFor(item.id)
                  return (
                    <li key={item.id} className="rounded-md border p-3" data-item-id={item.id}>
                      <p className="font-medium">{item.product_name}</p>
                      {/* La unidad va SIEMPRE junto a la cantidad (ej. "50 bolsas"). */}
                      <p className="text-sm text-muted-foreground">
                        {Number(item.quantity)} {item.product_unit}
                      </p>
                      {item.notes && <p className="text-sm text-muted-foreground">{item.notes}</p>}
                      <p className="pt-1 text-xs text-muted-foreground" data-item-photos={photos}>
                        {photos === 0
                          ? 'Sin fotos de este producto'
                          : `${photos} foto${photos === 1 ? '' : 's'} de este producto`}
                      </p>
                      {isDraft && (
                        <Button
                          type="button"
                          variant="outline"
                          className="mt-2 h-12 w-full"
                          data-testid={`open-camera-item-${item.id}`}
                          onClick={() => openCamera(item.id)}
                        >
                          Sacar foto de este producto
                        </Button>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="gap-4 rounded-lg p-4">
          <CardHeader className="p-0">
            <CardTitle className="text-base">Fotos de evidencia</CardTitle>
          </CardHeader>

          <CardContent className="flex flex-col gap-4 p-0">
            {evidence.length === 0 && pending.length === 0 && (
              <p className="text-sm text-muted-foreground">
                {isDraft
                  ? 'Todavía no sacaste fotos de este remito.'
                  : 'Este remito no tiene fotos de evidencia.'}
              </p>
            )}

            {(evidence.length > 0 || pending.length > 0) && (
              <ul className="grid grid-cols-2 gap-3" data-testid="evidence-list">
                {evidence.map((photo) => (
                  <li
                    key={`evidence-${photo.id}`}
                    data-evidence-id={photo.id}
                    data-evidence-item={photo.shipment_item ?? ''}
                  >
                    <img
                      src={photo.file_url}
                      alt={`Evidencia del remito #${shipment.id}`}
                      className="aspect-square w-full rounded-md border object-cover"
                    />
                    <p className="truncate pt-1 text-xs font-medium">
                      {photoLabel(photo.shipment_item)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatDate(photo.uploaded_at)}
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
                    <p className="truncate pt-1 text-xs font-medium">{photoLabel(photo.itemId)}</p>
                    {photo.state === 'uploading' ? (
                      <p className="pt-1 text-xs text-muted-foreground">Subiendo…</p>
                    ) : (
                      <div className="flex flex-col gap-2 pt-1">
                        <p role="alert" className="text-xs text-destructive">
                          No se pudo subir.
                        </p>
                        <Button
                          type="button"
                          className="h-12"
                          onClick={() => uploadPhoto(photo)}
                        >
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

            {/* La foto solo puede salir de la cámara en vivo: no hay input de archivo,
                así que no se puede adjuntar nada de la galería del dispositivo. */}
            {isDraft && (
              <Button
                type="button"
                className="h-12 w-full"
                data-testid="open-camera"
                onClick={() => openCamera(null)}
              >
                Sacar foto del remito
              </Button>
            )}
          </CardContent>
        </Card>

        {isDraft && (
          <>
            {hasUnconfirmedPhotos && (
              <p className="text-sm text-muted-foreground">
                Esperá a que terminen de subirse las fotos para poder despachar.
              </p>
            )}
            <Button
              type="button"
              className="h-12 w-full"
              data-testid="dispatch"
              disabled={hasUnconfirmedPhotos}
              onClick={() => {
                setDispatchError(null)
                setConfirmOpen(true)
              }}
            >
              Despachar
            </Button>
          </>
        )}

        {dispatchError && !confirmOpen && (
          <p role="alert" className="text-sm text-destructive">
            {dispatchError}
          </p>
        )}
      </main>

      {cameraOpen && (
        <CameraCapture onCapture={handleCapture} onClose={() => setCameraOpen(false)} />
      )}

      {/* Confirmación explícita: el despacho es irreversible (sección 6), así que un
          solo click no puede dispararlo. */}
      <Dialog open={confirmOpen} onOpenChange={(open) => !dispatching && setConfirmOpen(open)}>
        <DialogContent data-testid="dispatch-dialog">
          <DialogHeader>
            <DialogTitle>¿Despachar el remito #{shipment.id}?</DialogTitle>
            <DialogDescription>
              El despacho es irreversible: el remito queda inmutable y se genera el link para
              que {shipment.receiver_name} confirme la recepción.
              {evidence.length === 0
                ? ' Atención: este remito no tiene ninguna foto de evidencia.'
                : ` Se despacha con ${evidence.length} foto${evidence.length === 1 ? '' : 's'} de evidencia.`}
            </DialogDescription>
          </DialogHeader>

          {dispatchError && (
            <p role="alert" className="text-sm text-destructive">
              {dispatchError}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              className="h-12"
              disabled={dispatching}
              onClick={() => setConfirmOpen(false)}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              className="h-12"
              data-testid="dispatch-confirm"
              disabled={dispatching}
              onClick={handleDispatch}
            >
              {dispatching ? 'Despachando…' : 'Sí, despachar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
