/*
 * Canal de soporte que se le muestra al usuario en los puntos de fricción: la
 * pantalla de 404 (tarea 10.4) y el pie de los documentos legales (7.5 / 7.7).
 *
 * Son los MISMOS datos que publica la landing (frieselanding/lib/site.ts) y los
 * mismos que usa el backend (`SUPPORT_CONTACT_EMAIL` en config/settings.py): quien
 * recibe un email y después entra a la web tiene que encontrar el mismo contacto en
 * todos lados. Si se cambia acá, hay que cambiarlo en esos dos archivos.
 *
 * OJO — `contacto@friese.com.ar` todavía NO recibe correo: el dominio no tiene
 * registros MX. Hasta que se configure el reenvío, el canal que funciona de verdad
 * es el WhatsApp; por eso los dos se muestran siempre juntos.
 *
 * Van como constantes y no como variables de Vite: es información pública y una
 * variable más es una variable más para olvidarse de cargar en Vercel.
 */
export const SUPPORT_EMAIL = 'contacto@friese.com.ar'
export const SUPPORT_WHATSAPP_DISPLAY = '+54 9 3472 43-0136'
export const SUPPORT_WHATSAPP_URL = 'https://wa.me/5493472430136'
