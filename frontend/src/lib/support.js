/*
 * Canal de soporte que se le muestra al usuario en los puntos de fricción: la
 * pantalla de 404 (tarea 10.4) y el pie de los documentos legales (7.5 / 7.7).
 *
 * Son los MISMOS datos que publica la landing (frieselanding/lib/site.ts) y los
 * mismos que usa el backend (`SUPPORT_CONTACT_EMAIL` en config/settings.py): quien
 * recibe un email y después entra a la web tiene que encontrar el mismo contacto en
 * todos lados. Si se cambia acá, hay que cambiarlo en esos dos archivos.
 *
 * `contacto@friese.com.ar` SÍ recibe correo desde el 2026-09-05, vía Cloudflare
 * Email Routing (reenvío a la casilla de negocio). Es reenvío y no buzón: se recibe
 * ahí, pero responder desde esa dirección necesita configuración aparte. Los dos
 * canales se siguen mostrando juntos igual — en el depósito el WhatsApp gana.
 *
 * Van como constantes y no como variables de Vite: es información pública y una
 * variable más es una variable más para olvidarse de cargar en Vercel.
 */
export const SUPPORT_EMAIL = 'contacto@friese.com.ar'
export const SUPPORT_WHATSAPP_DISPLAY = '+54 9 3472 43-0136'
export const SUPPORT_WHATSAPP_URL = 'https://wa.me/5493472430136'
