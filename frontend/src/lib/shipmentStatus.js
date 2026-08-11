/*
 * Estados de remito y sus colores FIJOS en toda la plataforma (docs/diseno.md,
 * sección 2): draft=slate-400, dispatched=blue-500, accepted=green-500,
 * disputed=red-500, closed=slate-600. No usar otros colores para el estado.
 *
 * El badge es de color sólido (el color exacto del estado como fondo) y el texto se
 * elige por estado midiendo el contraste real contra ese relleno, no a ojo. Con la
 * paleta OKLCH de Tailwind v4 los únicos rellenos lo bastante oscuros para texto
 * blanco son slate-600 (7.58); en blue-500 y red-500 el blanco quedaba en 3.76 y 3.81,
 * bajo el 4.5 de WCAG AA, así que también llevan el fondo base oscuro (4.60 y 4.54).
 *
 *   slate-400 #90A1B9 + #1A1A22 → 6.57    green-500 #00C950 + #1A1A22 → 7.80
 *   blue-500  #2B7FFF + #1A1A22 → 4.60    red-500   #FB2C36 + #1A1A22 → 4.54
 *   slate-600 #45556C + #FFFFFF → 7.58
 */
export const SHIPMENT_STATUSES = [
  { value: 'draft', label: 'Borrador', badgeClass: 'bg-slate-400 text-background' },
  { value: 'dispatched', label: 'Despachado', badgeClass: 'bg-blue-500 text-background' },
  { value: 'accepted', label: 'Aceptado', badgeClass: 'bg-green-500 text-background' },
  { value: 'disputed', label: 'En disputa', badgeClass: 'bg-red-500 text-background' },
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
