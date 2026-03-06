import { Button } from "@/components/ui/button"
import Link from "next/link"
import { ArrowLeft } from "lucide-react"

export default function PrivacyPolicy() {
  return (
    <div className="min-h-screen bg-background text-foreground py-16 px-4 md:px-6">
      <div className="container mx-auto max-w-3xl space-y-12">
        
        {/* Botón para volver */}
        <Button variant="ghost" asChild className="mb-8 -ml-4 text-muted-foreground hover:text-foreground">
          <Link href="/">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Volver al inicio
          </Link>
        </Button>

        {/* Encabezado del documento */}
        <div className="space-y-4 border-b border-border pb-8">
          <h1 className="text-3xl md:text-4xl font-bold tracking-tighter">Política de Privacidad y Términos de Uso</h1>
          <p className="text-muted-foreground">Friese — Tu operación, bajo control.</p>
          <div className="flex flex-wrap gap-4 text-sm text-muted-foreground/80">
            <span>Versión 1.0</span>
            <span>·</span>
            <span>Argentina</span>
            <span>·</span>
            <span>2025</span>
          </div>
          
          <div className="mt-6 p-4 bg-muted/30 border border-border rounded-lg">
            <p className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">⚠ Aviso importante:</span> Este documento fue redactado como base de trabajo y debe ser revisado y validado por un abogado matriculado antes de su publicación oficial. Friese no asume responsabilidad legal por el uso de este borrador sin revisión profesional.
            </p>
          </div>
        </div>

        {/* Contenido legal */}
        <div className="space-y-8 text-muted-foreground leading-relaxed">
          
          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">1. Introducción</h2>
            <p>
              La presente Política de Privacidad y Términos de Uso (en adelante, "el Documento") regula el tratamiento de los datos personales recopilados por Friese (en adelante, "Friese", "nosotros" o "la Plataforma") a través de su sitio web y del formulario de lista de espera (wishlist) disponible en friese.com.ar (en adelante, "el Sitio").
            </p>
            <p>
              Al completar el formulario de lista de espera, el usuario declara haber leído, comprendido y aceptado los términos establecidos en el presente Documento. Si no estás de acuerdo con alguna de las condiciones aquí descritas, te pedimos que no completes el formulario.
            </p>
            <p>
              Friese se encuentra en etapa de desarrollo previo al lanzamiento comercial. Los datos recopilados a través de la lista de espera tienen como único fin gestionar el acceso anticipado a la plataforma y mantener informados a los interesados sobre el avance del producto.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">2. Responsable del tratamiento de datos</h2>
            <p>El responsable del tratamiento de los datos personales recopilados a través del Sitio es:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong className="text-foreground">Nombre comercial:</strong> Friese</li>
              <li><strong className="text-foreground">Titular:</strong> Ulises Baretta</li>
              <li><strong className="text-foreground">País de operación:</strong> República Argentina</li>
            </ul>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">3. Datos personales que recopilamos</h2>
            <p>A través del formulario de lista de espera, Friese recopila exclusivamente los siguientes datos personales:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong className="text-foreground">Dirección de correo electrónico:</strong> Canal principal de comunicación para notificar al usuario sobre el avance del producto y el acceso anticipado a la plataforma.</li>
              <li><strong className="text-foreground">Nombre de la empresa:</strong> Dato de contexto profesional que permite a Friese comprender el perfil del interesado y personalizar la comunicación.</li>
            </ul>
            <p>
              Friese no recopila datos sensibles en los términos del artículo 2 de la Ley N° 25.326 de Protección de los Datos Personales (datos de salud, orientación sexual, creencias religiosas u otros de naturaleza similar). No recopila datos de menores de 18 años. Si tomamos conocimiento de que un menor completó el formulario, procederemos a eliminar sus datos de inmediato.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">4. Finalidad del tratamiento</h2>
            <p>Los datos recopilados son utilizados exclusivamente para las siguientes finalidades:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li>Gestionar la lista de espera de acceso anticipado a la plataforma Friese.</li>
              <li>Informar al usuario sobre novedades, avances del producto, fechas de lanzamiento y condiciones de acceso anticipado.</li>
              <li>Contactar al usuario para coordinar el proceso de onboarding cuando la plataforma esté disponible.</li>
              <li>Analizar de forma agregada y anónima el perfil de los interesados para mejorar el desarrollo del producto.</li>
            </ul>
            <p>Friese no utilizará los datos recopilados para ninguna finalidad distinta a las mencionadas sin el consentimiento previo y expreso del titular.</p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">5. Base legal del tratamiento</h2>
            <p>
              El tratamiento de los datos personales se realiza sobre la base del consentimiento libre, expreso e informado del titular, conforme lo establece la Ley N° 25.326 de Protección de los Datos Personales de la República Argentina y su Decreto Reglamentario N° 1558/2001. Al completar y enviar el formulario de lista de espera, el usuario otorga dicho consentimiento.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">6. Almacenamiento y seguridad de los datos</h2>
            <p>
              Los datos recopilados son almacenados en plataformas de terceros que cumplen con estándares de seguridad reconocidos internacionalmente. Actualmente Friese utiliza los siguientes proveedores para la gestión de la lista de espera:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong className="text-foreground">Google Forms y Google Sheets:</strong> Plataformas de gestión de formularios y hojas de cálculo utilizadas para la recepción y almacenamiento estructurado de los contactos.</li>
            </ul>
            <p>
              Friese adopta medidas técnicas y organizativas razonables para proteger los datos personales contra accesos no autorizados, pérdida, alteración o divulgación indebida. Sin embargo, ningún sistema de transmisión o almacenamiento de datos por internet es completamente seguro. En caso de que tomemos conocimiento de una brecha de seguridad que afecte los datos de los usuarios, procederemos a notificarles en el menor tiempo posible.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">7. Plazo de retención de los datos</h2>
            <p>
              Los datos personales serán conservados mientras el usuario mantenga su inscripción en la lista de espera y hasta que Friese lo notifique del resultado de su solicitud de acceso anticipado. Una vez que la relación concluya (ya sea porque el usuario accede a la plataforma, solicita la baja o Friese decide dar por finalizada la lista de espera), los datos serán eliminados en un plazo máximo de 30 días, salvo que exista obligación legal de conservarlos por un período mayor.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">8. Derechos del titular de los datos</h2>
            <p>En cumplimiento de la Ley N° 25.326, el titular de los datos personales tiene derecho a:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong className="text-foreground">Acceso:</strong> Solicitar información sobre los datos personales que Friese tiene registrados sobre su persona.</li>
              <li><strong className="text-foreground">Rectificación:</strong> Solicitar la corrección de datos inexactos, incompletos o desactualizados.</li>
              <li><strong className="text-foreground">Supresión:</strong> Solicitar la eliminación de sus datos personales de nuestras bases de datos, en los casos previstos por la ley.</li>
              <li><strong className="text-foreground">Confidencialidad:</strong> Que sus datos sean tratados con la confidencialidad establecida en el presente Documento.</li>
              <li><strong className="text-foreground">Revocación del consentimiento:</strong> Retirar el consentimiento otorgado en cualquier momento, sin que ello afecte la licitud del tratamiento realizado con anterioridad.</li>
            </ul>
            <p>
              Para ejercer cualquiera de estos derechos, el usuario puede enviar una solicitud al correo electrónico de contacto indicado en la Sección 13, identificándose con la dirección de email con la que se registró. Friese responderá en un plazo máximo de 10 días hábiles.
            </p>
            <p>
              La Agencia de Acceso a la Información Pública (AAIP), en su carácter de órgano de control de la Ley N° 25.326, tiene la atribución de atender las denuncias y reclamos que interpongan quienes resulten afectados en sus derechos por incumplimiento de las normas vigentes en materia de protección de datos personales.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">9. Transferencia de datos a terceros</h2>
            <p>
              Friese no vende, cede ni transfiere los datos personales de los usuarios a terceros con fines comerciales. Los únicos terceros que pueden acceder a los datos son los proveedores de servicios tecnológicos mencionados en la Sección 6, en su carácter de encargados del tratamiento, y únicamente para las finalidades descritas en la Sección 4.
            </p>
            <p>
              En caso de que Friese sea requerida a divulgar información personal por orden judicial, mandato legal o requerimiento de autoridad competente, procederá a hacerlo en los términos y con los límites establecidos por la normativa aplicable.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">10. Cookies y tecnologías de seguimiento</h2>
            <p>
              El Sitio puede utilizar cookies técnicas necesarias para su correcto funcionamiento. En caso de utilizarse herramientas de analítica web (como Google Analytics u otras), el usuario será informado mediante un aviso de cookies visible al ingresar al Sitio. El usuario puede configurar su navegador para rechazar el uso de cookies, aunque esto podría afectar la experiencia de navegación.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">11. Modificaciones a este Documento</h2>
            <p>
              Friese se reserva el derecho de actualizar o modificar el presente Documento en cualquier momento. Cualquier modificación será publicada en el Sitio con indicación de la fecha de actualización. En caso de cambios sustanciales que afecten el tratamiento de los datos personales, notificaremos a los usuarios registrados por correo electrónico. El uso continuado del Sitio o la permanencia en la lista de espera tras la publicación de los cambios implica la aceptación de la nueva versión del Documento.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">12. Ley aplicable y jurisdicción</h2>
            <p>
              El presente Documento se rige por la legislación vigente en la República Argentina, en particular por la Ley N° 25.326 de Protección de los Datos Personales, su Decreto Reglamentario N° 1558/2001, y las disposiciones complementarias emanadas de la Agencia de Acceso a la Información Pública (AAIP).
            </p>
            <p>
              Para cualquier controversia derivada de la interpretación o aplicación del presente Documento, las partes se someten a la jurisdicción de los tribunales ordinarios de la Ciudad Autónoma de Buenos Aires, con renuncia expresa a cualquier otro fuero que pudiera corresponder.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-bold text-foreground">13. Contacto</h2>
            <p>
              Para cualquier consulta, reclamo o ejercicio de derechos relacionados con el presente Documento, el usuario puede comunicarse con Friese a través de:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong className="text-foreground">Correo electrónico:</strong> friesearg@gmail.com</li>
              <li><strong className="text-foreground">Sitio web:</strong> friese.com</li>
            </ul>
          </section>

        </div>

        {/* Footer del documento */}
        <div className="pt-8 border-t border-border mt-12 text-sm text-muted-foreground text-center">
          <p>Friese® — Tu operación, bajo control.</p>
          <p>Última actualización: 2025 · Versión 1.0 · Sujeto a revisión legal</p>
        </div>

      </div>
    </div>
  )
}