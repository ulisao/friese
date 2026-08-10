import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { api } from '@/lib/api'
import { SHIPMENT_STATUSES, getShipmentStatus } from '@/lib/shipmentStatus'
import { useAuthStore } from '@/store/auth'

const ALL = 'all'

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
 * Lista de remitos de la empresa del operador (tarea 2.6).
 * GET /api/shipments/ ya filtra por company del usuario autenticado, así que acá
 * no hay ninguna lógica de aislamiento: se muestra lo que devuelve la API.
 * El filtro por estado es del lado del cliente: el endpoint no está paginado ni
 * acepta ?status=, así que el navegador ya tiene la lista completa.
 */
export function ShipmentsPage() {
  const username = useAuthStore((state) => state.username)
  const clearSession = useAuthStore((state) => state.clearSession)

  const [shipments, setShipments] = useState([])
  const [status, setStatus] = useState('loading') // 'loading' | 'ready' | 'error'
  const [filter, setFilter] = useState(ALL)

  const load = useCallback(async () => {
    setStatus('loading')
    try {
      const { data } = await api.get('/shipments/')
      setShipments(Array.isArray(data) ? data : (data.results ?? []))
      setStatus('ready')
    } catch {
      setStatus('error')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const visible =
    filter === ALL ? shipments : shipments.filter((shipment) => shipment.status === filter)

  return (
    <div className="min-h-svh">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-2xl items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold">Remitos</h1>
            <p className="truncate text-sm text-muted-foreground">Operador: {username}</p>
          </div>
          <Button variant="outline" className="h-12" onClick={clearSession}>
            Salir
          </Button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-2xl px-4 pt-4 pb-8">
        <Button asChild className="h-12 w-full">
          <Link to="/remitos/nuevo">Nuevo remito</Link>
        </Button>

        {/* Filtro por estado. Targets h-12 (mobile-first, docs/diseno.md sección 5). */}
        <div className="-mx-4 mt-4 flex gap-2 overflow-x-auto px-4 pb-3">
          <Button
            variant={filter === ALL ? 'default' : 'outline'}
            className="h-12 px-4"
            aria-pressed={filter === ALL}
            onClick={() => setFilter(ALL)}
          >
            Todos
          </Button>

          {SHIPMENT_STATUSES.map((option) => (
            <Button
              key={option.value}
              variant={filter === option.value ? 'default' : 'outline'}
              className="h-12 px-4"
              aria-pressed={filter === option.value}
              onClick={() => setFilter(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </div>

        {status === 'loading' && <p className="py-8 text-sm text-muted-foreground">Cargando…</p>}

        {status === 'error' && (
          <div className="flex flex-col items-start gap-3 py-8">
            <p role="alert" className="text-sm text-destructive">
              No se pudieron cargar los remitos.
            </p>
            <Button variant="outline" className="h-12" onClick={load}>
              Reintentar
            </Button>
          </div>
        )}

        {status === 'ready' && visible.length === 0 && (
          <p className="py-8 text-sm text-muted-foreground">
            {shipments.length === 0
              ? 'Todavía no hay remitos.'
              : `No hay remitos en estado «${getShipmentStatus(filter).label}».`}
          </p>
        )}

        {status === 'ready' && visible.length > 0 && (
          <ul className="flex flex-col gap-3">
            {visible.map((shipment) => (
              <li key={shipment.id}>
                {/* La card entera es el link al detalle (tarea 2.8): target grande. */}
                <Link to={`/remitos/${shipment.id}`} className="block">
                  <Card className="gap-3 rounded-lg p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm text-muted-foreground">Remito #{shipment.id}</p>
                        <p className="truncate font-semibold">{shipment.receiver_name}</p>
                      </div>
                      <StatusBadge status={shipment.status} />
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Creado el {formatDate(shipment.created_at)}
                    </p>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  )
}
