"use client"

import { ShieldCheck, Route, ClipboardCheck, Database } from "lucide-react"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const capabilities = [
  {
    icon: ShieldCheck,
    title: "Evidencia certificada de envíos",
    description:
      "Registro fotográfico con timestamp, geolocalización y hash criptográfico para cada despacho.",
  },
  {
    icon: Route,
    title: "Cadena de custodia validada",
    description:
      "Trazá el recorrido completo: empresa, flete, cliente — con confirmación en cada punto.",
  },
  {
    icon: ClipboardCheck,
    title: "Portal de reclamos integrado",
    description:
      "Tu cliente confirma la recepción o abre un reclamo directo desde el portal, con toda la evidencia.",
  },
  {
    icon: Database,
    title: "Registro inmutable y auditable",
    description:
      "Cada operación queda documentada en un registro que no se puede alterar. Listo para auditoría.",
  },
]

export function SolutionSection() {
  const { ref, isVisible } = useScrollAnimation(0.1)

  return (
    <section
      id="plataforma"
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
            La plataforma
          </p>
          <h2
            className={`font-serif text-3xl font-bold tracking-tight text-foreground sm:text-4xl text-balance ${
              isVisible
                ? "animate-fade-up animation-delay-100"
                : "opacity-0"
            }`}
          >
            Una plataforma. Toda tu operación.
          </h2>
          <p
            className={`mt-4 text-lg leading-relaxed text-muted-foreground ${
              isVisible
                ? "animate-fade-up animation-delay-200"
                : "opacity-0"
            }`}
          >
            Todo lo que necesitás para que tu logística deje de ser un problema
            y se convierta en una ventaja competitiva.
          </p>
        </div>

        <div className="mt-16 grid gap-6 sm:grid-cols-2 lg:gap-8">
          {capabilities.map((cap, i) => (
            <div
              key={cap.title}
              className={`group rounded-lg border border-border bg-card/50 p-8 transition-all hover:border-primary/30 hover:bg-card ${
                isVisible
                  ? `animate-fade-up animation-delay-${(i + 1) * 100}`
                  : "opacity-0"
              }`}
            >
              <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-sm bg-primary/10 transition-colors group-hover:bg-primary/20">
                <cap.icon className="h-6 w-6 text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground">
                {cap.title}
              </h3>
              <p className="mt-2 text-base leading-relaxed text-muted-foreground">
                {cap.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
