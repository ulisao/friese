"""Rate limiting de los endpoints públicos del receptor (tarea 6.2).

Son los únicos endpoints sin autenticación del sistema: la única credencial es el
`public_token` del link, cualquiera con la URL puede pegarles y no hay usuario
detrás al que atribuirle el consumo. Por eso el cupo se cuenta por IP.

Se usan dos ventanas a la vez (el patrón burst/sustained de DRF): una corta
contra el martilleo inmediato y una larga contra el goteo sostenido. Las dos se
evalúan en cada request y basta que una se pase para devolver 429. Los valores
salen de `DEFAULT_THROTTLE_RATES` en settings, configurables por env.

Se hereda de AnonRateThrottle (no de SimpleRateThrottle a secas) porque ya
resuelve la clave por IP respetando NUM_PROXIES; en estos endpoints el usuario
es siempre anónimo (`authentication_classes = []`), así que nunca queda exento.

NOTA: el contador vive en el cache de Django, que hoy es el default en memoria
del proceso. Con varios workers de gunicorn cada uno lleva su propia cuenta y el
límite efectivo se multiplica por la cantidad de workers (y se reinicia en cada
deploy). Sigue cortando el abuso, pero para un límite exacto y compartido hace
falta un cache común (Redis) — ver pendientes de la tarea en PROGRESS.md.
"""

from rest_framework.throttling import AnonRateThrottle


class PublicBurstThrottle(AnonRateThrottle):
    """Ventana corta: corta la ráfaga (default 30/min)."""

    scope = "public_burst"


class PublicSustainedThrottle(AnonRateThrottle):
    """Ventana larga: corta el goteo sostenido (default 300/hour)."""

    scope = "public_sustained"


# Lista lista para usar como `throttle_classes` en las vistas públicas.
PUBLIC_THROTTLES = [PublicBurstThrottle, PublicSustainedThrottle]
