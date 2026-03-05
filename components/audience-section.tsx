"use client"

import { Factory, Truck, ShoppingCart } from "lucide-react"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const audiences = [
  {
    icon: Factory,
    title: "Fábricas y manufactura",
    description:
      "Documentá cada despacho de planta con evidencia que respalda tus entregas ante reclamos de clientes.",
  },
  {
    icon: Truck,
    title: "Distribuidoras",
    description:
      "Controlá la cadena de custodia completa y eliminá la incertidumbre en cada punto de entrega.",
  },
  {
    icon: ShoppingCart,
    title: "E-commerce con logística propia",
    description:
      "Reducí reclamos falsos y mejorá la experiencia post-compra con confirmación automática de entrega.",
  },
]

export function AudienceSection() {
  const { ref, isVisible } = useScrollAnimation(0.1)

  return (
    <section className="relative border-t border-border/50 py-24 lg:py-32" ref={ref}>
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="mx-auto max-w-2xl">
          <p
            className={`mb-3 text-sm font-semibold tracking-widest text-primary uppercase ${
              isVisible ? "animate-fade-up" : "opacity-0"
            }`}
          >
            {"Para quién es"}
          </p>
          <h2
            className={`font-serif text-3xl font-bold tracking-tight text-foreground sm:text-4xl text-balance ${
              isVisible
                ? "animate-fade-up animation-delay-100"
                : "opacity-0"
            }`}
          >
            Para equipos que operan en serio.
          </h2>
          <p
            className={`mt-4 text-lg leading-relaxed text-muted-foreground ${
              isVisible
                ? "animate-fade-up animation-delay-200"
                : "opacity-0"
            }`}
          >
            Si tu operación mueve mercadería y necesita certeza en cada entrega,
            DespachoApp está construido para vos.
          </p>
        </div>

        <div className="mt-12 grid gap-6 sm:grid-cols-3">
          {audiences.map((aud, i) => (
            <div
              key={aud.title}
              className={`rounded-lg border border-border bg-card/30 p-8 transition-all hover:border-primary/30 ${
                isVisible
                  ? `animate-fade-up animation-delay-${(i + 2) * 100}`
                  : "opacity-0"
              }`}
            >
              <aud.icon className="h-8 w-8 text-primary" />
              <h3 className="mt-4 text-lg font-semibold text-foreground">
                {aud.title}
              </h3>
              <p className="mt-2 text-base leading-relaxed text-muted-foreground">
                {aud.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
