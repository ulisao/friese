import { Link, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { SUPPORT_EMAIL, SUPPORT_WHATSAPP_DISPLAY, SUPPORT_WHATSAPP_URL } from '@/lib/support'
import { useDocumentTitle } from '@/lib/useDocumentTitle'

/*
 * Términos de Servicio y Política de Privacidad (tarea 7.5).
 *
 * SON UN BORRADOR. El enunciado de la tarea es explícito: esto es el punto de
 * partida para que lo revise un abogado, no el texto legal definitivo. Por eso
 * cada página abre con el aviso de versión preliminar, bien visible y arriba de
 * todo, y los puntos que dependen de esa revisión están marcados en el texto.
 *
 * Viven en el frontend y no en el backend porque los tiene que poder abrir
 * cualquiera: el receptor (que no tiene login y llega desde el link del email,
 * tarea 7.6), el operador, el admin de empresa desde el panel y la landing.
 *
 * Lo que dicen es lo que el sistema HACE de verdad: los datos que se listan son
 * los campos que existen en los modelos, y los proveedores son los que están
 * configurados. Si algo de eso cambia, este texto cambia con ello.
 */

const LEGAL_VERSION = 'v1-borrador'
const LEGAL_UPDATED = '29 de agosto de 2026'

function Aviso() {
  return (
    <div
      role="status"
      data-testid="legal-draft-notice"
      className="rounded-md border border-amber-500/60 bg-amber-500/10 p-4"
    >
      <p className="text-sm font-semibold text-amber-400">
        Versión preliminar, pendiente de revisión legal
      </p>
      <p className="pt-1 text-sm text-muted-foreground">
        Este documento es un borrador de trabajo. Todavía no fue revisado por un abogado, así
        que no es el texto definitivo del servicio. Lo publicamos para que se pueda leer desde
        ahora qué hacemos con la información; cuando la revisión termine, esta misma página se
        reemplaza por la versión final.
      </p>
    </div>
  )
}

function Seccion({ titulo, children }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold">{titulo}</h2>
      {children}
    </section>
  )
}

function Documento({ titulo, otro, children }) {
  const navigate = useNavigate()

  return (
    <div className="min-h-svh">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <img src="/friese-mark.png" alt="" width="32" height="32" className="h-8 w-8" />
            <h1 className="truncate text-xl font-semibold">{titulo}</h1>
          </div>
          <Button variant="outline" className="h-12 shrink-0" onClick={() => navigate(-1)}>
            Volver
          </Button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 pt-4 pb-12">
        <Aviso />

        <p className="text-sm text-muted-foreground">
          Versión {LEGAL_VERSION} · Última actualización: {LEGAL_UPDATED}
        </p>

        {children}

        <Seccion titulo="Cómo contactarnos">
          <p className="text-sm text-muted-foreground">
            Por cualquier duda sobre este documento, escribinos a{' '}
            <a className="underline" href={`mailto:${SUPPORT_EMAIL}`}>
              {SUPPORT_EMAIL}
            </a>{' '}
            o por WhatsApp al{' '}
            <a className="underline" href={SUPPORT_WHATSAPP_URL}>
              {SUPPORT_WHATSAPP_DISPLAY}
            </a>
            .
          </p>
        </Seccion>

        <p className="border-t pt-4 text-sm">
          <Link className="underline" to={otro.to}>
            {otro.label}
          </Link>
        </p>
      </main>
    </div>
  )
}

const P = ({ children }) => (
  <p className="text-sm leading-relaxed text-muted-foreground">{children}</p>
)

const Lista = ({ children }) => (
  <ul className="flex list-disc flex-col gap-1 pl-5 text-sm leading-relaxed text-muted-foreground">
    {children}
  </ul>
)

export function TermsPage() {
  useDocumentTitle('Términos de Servicio')

  return (
    <Documento
      titulo="Términos de Servicio"
      otro={{ to: '/privacidad', label: 'Ver la Política de Privacidad' }}
    >
      <Seccion titulo="1. Qué es Friese">
        <P>
          Friese es un servicio que registra la evidencia de una entrega. La empresa que
          despacha carga un remito, le saca fotos con la cámara del celular en el momento del
          despacho, y el destinatario recibe un link único por email para ver esas fotos y
          dejar su conformidad o reportar un problema.
        </P>
        <P>
          Cada foto se guarda tal como llega, con la fecha y la hora del servidor y con una
          huella digital (SHA-256) del archivo. Eso permite demostrar después que la foto
          que está guardada es exactamente la que se subió, sin cambios.
        </P>
      </Seccion>

      <Seccion titulo="2. Quién puede usarlo">
        <P>
          El servicio es para empresas. La empresa cliente contrata el servicio y da de alta a
          sus propios usuarios: administradores, que manejan el panel, y operadores, que cargan
          los remitos desde el celular.
        </P>
        <P>
          El destinatario de una entrega no se registra ni contrata nada: solo abre el link que
          le llega y responde. Su uso del link se rige por estos términos en lo que le aplique.
        </P>
      </Seccion>

      <Seccion titulo="3. Cuentas y accesos">
        <Lista>
          <li>
            Cada usuario entra con su propio nombre de usuario y contraseña. Las cuentas son
            individuales y no se comparten entre personas ni entre dispositivos.
          </li>
          <li>
            La empresa es responsable de lo que hagan sus usuarios con sus cuentas y de darlos
            de baja cuando dejan de trabajar con ella.
          </li>
          <li>
            Cada empresa ve únicamente sus propios datos. El aislamiento entre empresas está
            implementado en el sistema y no depende de que nadie recuerde filtrar.
          </li>
        </Lista>
      </Seccion>

      <Seccion titulo="4. Qué hace Friese y qué no hace">
        <P>Friese registra, conserva y muestra la evidencia. Eso es todo lo que hace.</P>
        <Lista>
          <li>
            No verificamos qué hay adentro de la carga, ni si lo que muestra la foto es lo que
            dice el remito. La foto la saca la empresa que despacha.
          </li>
          <li>
            No somos parte de la relación comercial entre la empresa y su cliente, ni árbitros
            de una discusión entre ellos. Si hay un reclamo, lo que aportamos es el registro.
          </li>
          <li>
            No emitimos documentos fiscales ni reemplazamos al remito legal que exija la
            normativa aplicable a cada empresa.
          </li>
        </Lista>
      </Seccion>

      <Seccion titulo="5. La evidencia y su conservación">
        <Lista>
          <li>
            Las fotos se guardan sin reprocesar, con su huella SHA-256 calculada al momento de
            recibirlas y la fecha y hora del servidor.
          </li>
          <li>
            Un remito despachado es inmutable: no se puede editar ni borrar desde la aplicación.
          </li>
          <li>
            Todo cambio hecho desde el panel de administración queda registrado en un historial
            con el autor, la fecha y el valor anterior.
          </li>
          <li>
            Si el destinatario no responde dentro de las 48 horas de abrir el link, el remito se
            cierra automáticamente y queda registrado como aceptado por silencio, distinguible
            de una conformidad expresa.
          </li>
          <li>
            Hacemos copias de resguardo periódicas de la base de datos y de las fotos. Esas
            copias son para recuperar el servicio ante una falla, no un archivo histórico
            garantizado.
          </li>
        </Lista>
      </Seccion>

      <Seccion titulo="6. Disponibilidad del servicio">
        <P>
          El servicio se presta tal como está y hacemos lo razonable para que esté disponible,
          pero no garantizamos funcionamiento ininterrumpido ni libre de errores. Puede haber
          interrupciones por mantenimiento o por fallas de los proveedores de infraestructura.
        </P>
      </Seccion>

      <Seccion titulo="7. Uso y facturación">
        <P>
          El uso se mide por remitos despachados por mes. Cada empresa arranca con una cantidad
          de remitos de prueba sin cargo, y a partir de ahí el consumo del mes determina el
          tramo de facturación acordado con la empresa. Cada empresa puede ver su propio consumo
          en el panel.
        </P>
        <P>
          Ante una falta de pago, el acceso de la empresa puede ser suspendido. La evidencia ya
          registrada no se elimina por ese motivo.
        </P>
      </Seccion>

      <Seccion titulo="8. Baja del servicio">
        <P>
          La empresa puede dar de baja el servicio cuando quiera. Qué pasa con los remitos y las
          fotos ya registrados después de la baja —cuánto tiempo se conservan y en qué formato
          se entregan— es uno de los puntos que quedan sujetos a la revisión legal de este
          borrador.
        </P>
      </Seccion>

      <Seccion titulo="9. Límite de responsabilidad">
        <P>
          Friese no responde por el valor de la mercadería, por el resultado de una discusión
          comercial entre la empresa y su cliente, ni por decisiones tomadas a partir de la
          evidencia registrada. Nuestra responsabilidad se limita a prestar el servicio de
          registro descrito acá.
        </P>
        <P>
          El alcance exacto de este límite es otro de los puntos pendientes de la revisión
          legal.
        </P>
      </Seccion>

      <Seccion titulo="10. Cambios en estos términos">
        <P>
          Si cambiamos estos términos, actualizamos la versión y la fecha del encabezado y le
          avisamos a las empresas clientes por email. La versión aceptada por cada empresa queda
          registrada de nuestro lado.
        </P>
      </Seccion>

      <Seccion titulo="11. Ley aplicable">
        <P>
          El servicio se presta desde la República Argentina y se rige por su legislación. La
          jurisdicción específica queda sujeta a la revisión legal de este borrador.
        </P>
      </Seccion>
    </Documento>
  )
}

export function PrivacyPage() {
  useDocumentTitle('Política de Privacidad')

  return (
    <Documento
      titulo="Política de Privacidad"
      otro={{ to: '/terminos', label: 'Ver los Términos de Servicio' }}
    >
      <Seccion titulo="1. Quién trata los datos">
        <P>
          Friese, como prestador del servicio de registro de entregas, trata los datos que se
          describen abajo. Las empresas clientes deciden qué entregas registran y a quién le
          mandan el link; nosotros procesamos esa información para prestarles el servicio.
        </P>
      </Seccion>

      <Seccion titulo="2. Qué datos se registran">
        <P>De la empresa cliente:</P>
        <Lista>
          <li>Nombre o razón social, email y teléfono de contacto.</li>
          <li>Su plan, su consumo mensual y la fecha en que aceptó estos documentos.</li>
        </Lista>

        <P>De los usuarios de la empresa (administradores y operadores):</P>
        <Lista>
          <li>
            Nombre de usuario, email y contraseña. La contraseña se guarda cifrada con un hash
            de una sola vía: no la podemos leer ni recuperar, solo se puede reemplazar.
          </li>
          <li>La fecha del último ingreso y qué remitos y fotos cargó cada uno.</li>
          <li>
            El historial de los cambios que hace desde el panel de administración, con el autor
            y la fecha. Es un registro de auditoría.
          </li>
        </Lista>

        <P>Del destinatario de la entrega:</P>
        <Lista>
          <li>
            Su nombre, email y teléfono, tal como los carga la empresa que despacha. El
            destinatario no completa ningún formulario de registro.
          </li>
          <li>El momento en que abre por primera vez el link del remito.</li>
          <li>
            Su respuesta: la conformidad o el reclamo, el texto que escriba y las fotos que saque
            de la mercadería recibida.
          </li>
        </Lista>

        <P>Datos técnicos:</P>
        <Lista>
          <li>
            La dirección IP desde la que se abre el link público, usada para limitar el abuso
            automatizado sobre esos endpoints.
          </li>
          <li>
            Una cookie técnica de sesión —que el navegador no deja leer desde JavaScript— para
            mantener al usuario logueado, y el nombre de usuario guardado en el propio navegador
            para no tener que volver a escribirlo. No usamos cookies de publicidad ni de
            seguimiento de terceros.
          </li>
        </Lista>
      </Seccion>

      <Seccion titulo="3. Las fotos">
        <P>
          Las fotos se guardan tal como las manda el dispositivo, sin reprocesarlas, así que
          pueden conservar los metadatos que traiga la cámara. La aplicación pide la foto con la
          cámara en el momento, no desde la galería del teléfono.
        </P>
        <P>
          De cada foto se calcula una huella SHA-256 al recibirla y se registra la fecha y hora
          del servidor. Eso es lo que permite demostrar después que el archivo no cambió.
        </P>
      </Seccion>

      <Seccion titulo="4. Para qué se usan">
        <Lista>
          <li>Registrar la entrega y dejar disponible la evidencia para las dos partes.</li>
          <li>
            Mandar los emails del servicio: el link al destinatario, el recordatorio si no lo
            abre, el aviso a la empresa si hay un reclamo y la confirmación del cierre.
          </li>
          <li>Medir el consumo mensual de cada empresa para facturarle.</li>
          <li>Atender los pedidos de soporte.</li>
        </Lista>
        <P>
          No vendemos ni cedemos estos datos, y no los usamos para publicidad ni para armar
          perfiles.
        </P>
      </Seccion>

      <Seccion titulo="5. Dónde se guardan y quién más los procesa">
        <P>
          Para prestar el servicio nos apoyamos en proveedores de infraestructura, que procesan
          los datos por cuenta nuestra y solo para eso:
        </P>
        <Lista>
          <li>Supabase — la base de datos.</li>
          <li>Cloudflare R2 — las fotos y las copias de resguardo.</li>
          <li>Railway — el servidor de la aplicación.</li>
          <li>Vercel — la aplicación web.</li>
          <li>Resend — el envío de los emails.</li>
        </Lista>
        <P>
          Estos proveedores operan servidores fuera de la Argentina, así que los datos se
          almacenan y procesan en el exterior. Las condiciones de esa transferencia son uno de
          los puntos sujetos a la revisión legal de este borrador.
        </P>
      </Seccion>

      <Seccion titulo="6. Cuánto tiempo se conservan">
        <Lista>
          <li>
            Los remitos, las fotos y su historial se conservan mientras la empresa sea cliente:
            son la evidencia de entregas que pueden discutirse mucho después. Hoy no se borran
            solos.
          </li>
          <li>
            Las copias de resguardo de la base se conservan alrededor de 30 días y después se
            van descartando.
          </li>
          <li>
            El plazo definitivo de conservación, y qué pasa cuando una empresa se da de baja,
            quedan sujetos a la revisión legal de este borrador.
          </li>
        </Lista>
      </Seccion>

      <Seccion titulo="7. Tus derechos">
        <P>
          Cualquier persona cuyos datos estén registrados puede pedir acceder a ellos,
          corregirlos si están mal o pedir que se eliminen, escribiéndonos a la casilla de abajo.
          Si los datos los cargó una empresa cliente —por ejemplo, el nombre y el email de un
          destinatario—, vamos a coordinar el pedido con ella.
        </P>
        <P>
          En la Argentina, la Agencia de Acceso a la Información Pública es el organismo de
          control de la Ley 25.326 de Protección de los Datos Personales y atiende las denuncias
          de quien considere afectados sus derechos. El texto exacto de esta sección es otro de
          los puntos pendientes de la revisión legal.
        </P>
      </Seccion>

      <Seccion titulo="8. Seguridad">
        <Lista>
          <li>Todo el tráfico viaja cifrado por HTTPS.</li>
          <li>Las contraseñas se guardan hasheadas y nunca en texto plano.</li>
          <li>Cada empresa está aislada de las demás dentro del sistema.</li>
          <li>
            Las fotos tienen huella digital y los cambios del panel quedan auditados con su
            autor.
          </li>
        </Lista>
        <P>
          Ningún sistema es infalible: esto reduce el riesgo, no lo elimina. Si detectamos un
          incidente que afecte datos de nuestros clientes, se los vamos a comunicar.
        </P>
      </Seccion>

      <Seccion titulo="9. Cambios en esta política">
        <P>
          Si cambia, actualizamos la versión y la fecha del encabezado. Las empresas clientes
          reciben aviso por email.
        </P>
      </Seccion>
    </Documento>
  )
}
