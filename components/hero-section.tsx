"use client"

import { ArrowRight } from "lucide-react"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

export function HeroSection() {
  const { ref, isVisible } = useScrollAnimation(0.1)

  const scrollToWaitlist = () => {
    document.getElementById("waitlist")?.scrollIntoView({ behavior: "smooth" })
  }

  return (
    <section
      ref={ref}
      className="relative flex min-h-screen items-center overflow-hidden pt-20"
    >
      {/* Background image — high contrast warehouse */}
      <div className="absolute inset-0 z-0">
        <img
          src="https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=2000&q=80"
          alt="Operaciones de almacén y logística industrial"
          className="h-full w-full object-cover opacity-15"
          crossOrigin="anonymous"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/95 to-background/70" />
      </div>

      <div className="relative z-10 mx-auto w-full max-w-7xl px-6 lg:px-8">
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
          {/* Left — copy */}
          <div
            className={`max-w-2xl ${
              isVisible ? "animate-fade-up" : "opacity-0"
            }`}
          >
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-secondary/50 px-4 py-1.5">
              <span className="h-2 w-2 rounded-full bg-primary" />
              <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Acceso anticipado abierto
              </span>
            </div>

            <h1 className="font-serif text-4xl font-bold leading-tight tracking-tight text-foreground sm:text-5xl lg:text-6xl text-balance">
              Convertí tu operación logística en tu activo más sólido.
            </h1>

            <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground lg:text-xl">
              Plataforma de inteligencia logística con trazabilidad completa,
              evidencia certificada y gestión de reclamos — para empresas que
              no pueden permitirse perder.
            </p>

            <div className="mt-10 flex flex-col gap-4 sm:flex-row sm:items-center">
              <button
                onClick={scrollToWaitlist}
                className="group flex items-center justify-center gap-2 rounded-sm bg-primary px-8 py-4 text-base font-semibold text-primary-foreground transition-all hover:brightness-110"
              >
                Reservar mi lugar
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </button>
            </div>
          </div>

          {/* Right — product visual */}
          <div
            className={`hidden lg:block ${
              isVisible
                ? "animate-fade-up animation-delay-300"
                : "opacity-0"
            }`}
          >
            <div className="relative">
              <div className="overflow-hidden rounded-lg border border-border bg-card shadow-2xl shadow-primary/5">
                <img
                  src="https://images.unsplash.com/photo-1553413077-190dd305871c?auto=format&fit=crop&w=1200&q=80"
                  alt="Dashboard de gestión logística profesional"
                  className="w-full object-cover opacity-90"
                  crossOrigin="anonymous"
                />
                {/* Overlay to simulate dashboard */}
                <div className="absolute inset-0 bg-gradient-to-t from-card via-transparent to-transparent" />
                <div className="absolute bottom-0 left-0 right-0 p-6">
                  <div className="flex items-center gap-3">
                    <div className="h-3 w-3 rounded-full bg-primary" />
                    <span className="text-sm font-medium text-foreground">
                      12 envíos en tránsito — 3 requieren atención
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-3">
                    {[
                      { label: "Completados", value: "847" },
                      { label: "En tránsito", value: "12" },
                      { label: "Reclamos", value: "2" },
                    ].map((stat) => (
                      <div
                        key={stat.label}
                        className="rounded-sm bg-secondary/80 px-3 py-2"
                      >
                        <p className="text-xs text-muted-foreground">
                          {stat.label}
                        </p>
                        <p className="text-lg font-bold text-foreground">
                          {stat.value}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
