import { NextResponse } from 'next/server';
import { Resend } from 'resend';

// Inicializamos Resend con la variable de entorno
const resend = new Resend(process.env.RESEND_API_KEY);

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { email } = body;

    if (!email) {
      return NextResponse.json(
        { error: 'El email es requerido' }, 
        { status: 400 }
      );
    }

    // Enviamos el email usando Resend
    const { data, error } = await resend.emails.send({
      from: 'Acme <onboarding@resend.dev>', // Email de prueba de Resend
      to: email, // Le mandamos el correo al usuario que se anotó
      subject: '¡Bienvenido a la lista de espera!',
      html: `
        <div style="font-family: sans-serif; color: #333;">
          <h2>¡Hola! 👋</h2>
          <p>Gracias por sumarte a nuestra lista de espera. Estamos trabajando duro en el proyecto y te vamos a avisar apenas tengamos novedades.</p>
          <br/>
          <p>Saludos,</p>
          <p><strong>El equipo</strong></p>
        </div>
      `,
    });

    if (error) {
      console.error("Error de Resend:", error);
      return NextResponse.json(
        { error: 'Hubo un problema al enviar el email' }, 
        { status: 500 }
      );
    }

    return NextResponse.json(
      { success: true, message: 'Email registrado y enviado correctamente' }, 
      { status: 200 }
    );

  } catch (error) {
    console.error("Error en el endpoint de waitlist:", error);
    return NextResponse.json(
      { error: 'Error interno del servidor' }, 
      { status: 500 }
    );
  }
}