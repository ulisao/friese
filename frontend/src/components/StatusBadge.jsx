import { cn } from '@/lib/utils'
import { getShipmentStatus } from '@/lib/shipmentStatus'

// Badge de estado del remito. El color sale siempre de shipmentStatus.js
// (colores fijos de docs/diseno.md sección 2).
export function StatusBadge({ status, className }) {
  const { label, badgeClass } = getShipmentStatus(status)

  return (
    <span
      data-status={status}
      className={cn(
        'inline-flex shrink-0 items-center rounded-md px-2.5 py-1 text-xs font-semibold whitespace-nowrap',
        badgeClass,
        className,
      )}
    >
      {label}
    </span>
  )
}
