/*
 * Estados de remito y sus colores FIJOS en toda la plataforma (docs/diseno.md,
 * sección 2): draft=slate-400, dispatched=blue-500, accepted=green-500,
 * disputed=red-500, closed=slate-600. No usar otros colores para el estado.
 *
 * El badge es de color sólido (el color exacto del estado como fondo) y el texto
 * se elige por estado para que se lea: sobre los tonos claros (slate-400,
 * green-500) va el fondo base oscuro; sobre los oscuros (blue-500, red-500,
 * slate-600) va blanco.
 */
export const SHIPMENT_STATUSES = [
  { value: 'draft', label: 'Borrador', badgeClass: 'bg-slate-400 text-background' },
  { value: 'dispatched', label: 'Despachado', badgeClass: 'bg-blue-500 text-white' },
  { value: 'accepted', label: 'Aceptado', badgeClass: 'bg-green-500 text-background' },
  { value: 'disputed', label: 'En disputa', badgeClass: 'bg-red-500 text-white' },
  { value: 'closed', label: 'Cerrado', badgeClass: 'bg-slate-600 text-white' },
]

// Si el backend devolviera un estado desconocido, se muestra tal cual en gris
// neutro en vez de romper la lista.
export function getShipmentStatus(value) {
  return (
    SHIPMENT_STATUSES.find((status) => status.value === value) ?? {
      value,
      label: value ?? '—',
      badgeClass: 'bg-muted text-muted-foreground',
    }
  )
}
