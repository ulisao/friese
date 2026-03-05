"use client"

import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const steps = [
  {
    number: "01",
    title: "Registrá el envío",
    description:
      "El operario registra el despacho y captura la evidencia fotográfica desde la app. Todo se certifica automáticamente.",
  },
  {
    number: "02",
    title: "Certificación automática",
    description:
      "El sistema genera un hash criptográfico, registra la ubicación y el timestamp, y notifica al receptor en tiempo real.",
  },
  {
    number: "03",
    title: "Confirmación o reclamo",
    description:
      "El cliente confirma la recepción desde el portal o abre un reclamo con toda la evidencia disponible. Sin llamadas, sin WhatsApp.",
  },
]

export function HowItWorksSection() {
  const { ref, isVisible } = useScrollAnimation(0.1)

  return (
    <section
      id="como-funciona"
      className="relative border-t border-border/50 py-24 lg:py-32"
      ref={ref}
    >
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p
            className={`mb-3 text-sm font-semibold tracking-widest text-primary uppercase ${
              isVisible ? "animate-fade-up" : "opacity-0"
            }`}
          >
            Cómo funciona
          </p>
          <h2
            className={`font-serif text-3xl font-bold tracking-tight text-foreground sm:text-4xl text-balance ${
              isVisible
                ? "animate-fade-up animation-delay-100"
                : "opacity-0"
            }`}
          >
            Tres pasos. Cero ambigüedad.
          </h2>
        </div>

        <div className="mt-16 grid gap-8 lg:grid-cols-3">
          {steps.map((step, i) => (
            <div
              key={step.number}
              className={`relative ${
                isVisible
                  ? `animate-fade-up animation-delay-${(i + 2) * 100}`
                  : "opacity-0"
              }`}
            >
              {/* Connector line — only between steps on desktop */}
              {i < steps.length - 1 && (
                <div className="absolute right-0 top-12 hidden h-px w-8 translate-x-full bg-border lg:block" />
              )}

              <div className="rounded-lg border border-border bg-card/30 p-8">
                <span className="font-serif text-5xl font-bold text-primary/30">
                  {step.number}
                </span>
                <h3 className="mt-4 text-xl font-semibold text-foreground">
                  {step.title}
                </h3>
                <p className="mt-3 text-base leading-relaxed text-muted-foreground">
                  {step.description}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Product screenshot placeholder */}
        <div
          className={`mt-16 overflow-hidden rounded-lg border border-border ${
            isVisible ? "animate-fade-up animation-delay-500" : "opacity-0"
          }`}
        >
          <img
            src="https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=2000&q=80"
            alt="Interfaz de software profesional para operaciones logísticas"
            className="w-full object-cover opacity-80 grayscale-[20%]"
            crossOrigin="anonymous"
          />
        </div>
      </div>
    </section>
  )
}
