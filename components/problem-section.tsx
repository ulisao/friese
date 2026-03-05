"use client"

import { MessageSquareWarning, FileQuestion, Sheet } from "lucide-react"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const painPoints = [
  {
    icon: MessageSquareWarning,
    text: "Tu equipo usa WhatsApp para documentar envíos de millones de pesos.",
  },
  {
    icon: FileQuestion,
    text: "Cuando surge un reclamo, no tenés ninguna prueba verificable.",
  },
  {
    icon: Sheet,
    text: "Los datos de tu operación logística viven en planillas, papeles y grupos de chat.",
  },
]

export function ProblemSection() {
  const { ref, isVisible } = useScrollAnimation(0.1)

  return (
    <section id="problema" className="relative py-24 lg:py-32" ref={ref}>
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-20">
          {/* Image */}
          <div
            className={`relative overflow-hidden rounded-lg ${
              isVisible ? "animate-fade-up" : "opacity-0"
            }`}
          >
            <img
              src="https://images.unsplash.com/photo-1565891741441-64926e441838?auto=format&fit=crop&w=1200&q=80"
              alt="Equipo de operaciones en almacén de logística"
              className="w-full object-cover grayscale-[30%] contrast-110"
              crossOrigin="anonymous"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-background/60 to-transparent" />
          </div>

          {/* Pain points */}
          <div>
            <p
              className={`mb-3 text-sm font-semibold tracking-widest text-primary uppercase ${
                isVisible ? "animate-fade-up" : "opacity-0"
              }`}
            >
              El problema
            </p>
            <h2
              className={`font-serif text-3xl font-bold tracking-tight text-foreground sm:text-4xl text-balance ${
                isVisible
                  ? "animate-fade-up animation-delay-100"
                  : "opacity-0"
              }`}
            >
              Tu operación logística funciona. Pero no tenés cómo probarlo.
            </h2>

            <div className="mt-10 flex flex-col gap-6">
              {painPoints.map((point, i) => (
                <div
                  key={i}
                  className={`flex gap-4 rounded-lg border border-border bg-card/50 p-5 ${
                    isVisible
                      ? `animate-fade-up animation-delay-${(i + 2) * 100}`
                      : "opacity-0"
                  }`}
                >
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm bg-primary/10">
                    <point.icon className="h-5 w-5 text-primary" />
                  </div>
                  <p className="text-base leading-relaxed text-secondary-foreground">
                    {point.text}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
