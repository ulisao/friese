"""Rate limiting de la recuperación de contraseña (tarea 7.4).

Los dos endpoints del flujo son públicos (el que olvidó la contraseña no tiene
sesión), así que el cupo se cuenta por IP, igual que en los endpoints del
receptor (shipments/throttling.py).

Qué corta cada uno:

- el de pedido, que un script use la casilla de un usuario real como buzón de
  spam, o que alguien barra usuarios a ver cuál existe (aunque la respuesta es
  siempre la misma, el tiempo de respuesta no lo es: mandar un email tarda);
- el de confirmación, la fuerza bruta contra el token del link.

El cupo es por IP y no por usuario a propósito: un depósito entero puede salir
por una sola IP, así que los valores son holgados para un humano que se
equivoca varias veces y cortos para un script. Salen de `DEFAULT_THROTTLE_RATES`
en settings, configurables por env.
"""

from rest_framework.throttling import AnonRateThrottle


class PasswordResetThrottle(AnonRateThrottle):
    """Cupo compartido por el pedido y la confirmación (default 20/hora por IP)."""

    scope = "password_reset"


PASSWORD_RESET_THROTTLES = [PasswordResetThrottle]
