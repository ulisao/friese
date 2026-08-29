"""Métricas del mes en curso para el índice del Django Admin (tarea 10.2).

Los números salen de lo que ya existe, sin contadores nuevos ni modelos nuevos:

- el estado de los remitos, de `Shipment.status` (docs/Desarrollo.md sección 3);
- las fotos cargadas, de `UsageLog.photos_uploaded`, que es el contador que ya
  alimenta el signal de evidencia (sección 6).

"Del mes en curso" es el mes calendario en la zona horaria del proyecto, el mismo
criterio con el que `companies.usage.increment_usage()` arma la clave "YYYY-MM"
del UsageLog: así el mes de las tarjetas y el mes del contador de fotos son
exactamente el mismo período.
"""

from django.db.models import Count, Sum
from django.utils import timezone

from companies.models import UsageLog

from .models import Shipment


def mes_en_curso(ahora=None):
    """(inicio, fin, clave) del mes calendario de `ahora` en la TZ del proyecto.

    `fin` es el primer instante del mes siguiente (rango semiabierto) y `clave` el
    "YYYY-MM" con el que se guarda el UsageLog.
    """
    inicio = timezone.localtime(ahora or timezone.now()).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    if inicio.month == 12:
        fin = inicio.replace(year=inicio.year + 1, month=1)
    else:
        fin = inicio.replace(month=inicio.month + 1)
    return inicio, fin, inicio.strftime("%Y-%m")


def metricas_del_mes(company_id=None, ahora=None):
    """Números del mes en curso. `company_id=None` = todas las empresas.

    El llamador es el que decide el alcance: el índice del admin le pasa siempre la
    empresa del usuario logueado, salvo al superadmin de Friese (tarea 4.1).

    Un remito cuenta en el mes en el que se DESPACHÓ (`dispatched_at`), no en el que
    se creó: hasta el despacho es un borrador que no salió del depósito, y es el
    mismo instante con el que el signal de despacho ubica el UsageLog.
    """
    inicio, fin, clave = mes_en_curso(ahora)

    remitos = Shipment.objects.filter(dispatched_at__gte=inicio, dispatched_at__lt=fin)
    usos = UsageLog.objects.filter(month=clave)
    if company_id is not None:
        remitos = remitos.filter(company_id=company_id)
        usos = usos.filter(company_id=company_id)

    por_estado = {
        fila["status"]: fila["n"]
        for fila in remitos.values("status").annotate(n=Count("id"))
    }
    total = sum(por_estado.values())
    pendientes = por_estado.get(Shipment.DISPATCHED, 0)
    aceptados = por_estado.get(Shipment.ACCEPTED, 0)
    disputados = por_estado.get(Shipment.DISPUTED, 0)

    tarjetas = [
        # "Pendiente de respuesta" es exactamente el remito que sigue en
        # `dispatched`: ya salió y el receptor todavía no aceptó ni se quejó.
        {"label": "Pendientes de respuesta", "valor": pendientes},
        {"label": "Aceptados", "valor": aceptados},
        {"label": "En disputa", "valor": disputados},
    ]
    # Hoy ningún código escribe `closed` y un remito despachado no vuelve a
    # borrador, así que este bucket queda en 0 y no se dibuja. Está para que la
    # suma de las tarjetas SIEMPRE dé el total, aunque alguien mueva un estado a
    # mano desde el panel.
    otros = total - pendientes - aceptados - disputados
    if otros:
        tarjetas.append({"label": "En otro estado", "valor": otros})

    return {
        "inicio": inicio,
        "total": total,
        "tarjetas": tarjetas,
        "fotos": usos.aggregate(n=Sum("photos_uploaded"))["n"] or 0,
    }
