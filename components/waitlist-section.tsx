"use client"

import { useState, type FormEvent } from "react"
import { ArrowRight, CheckCircle2 } from "lucide-react"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

export function WaitlistSection() {
  const { ref, isVisible } = useScrollAnimation(0.1)
  const [email, setEmail] = useState("")
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    setError("")

    if (!email) {
      setError("Ingresá tu email.")
      return
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email)) {
      setError("Ingresá un email válido.")
      return
    }

    // Simulate submission
    setSubmitted(true)
  }

  return (
    <section
      id="waitlist"
      className="relative border-t border-border/50 bg-secondary py-24 lg:py-32"
      ref={ref}
    >
      {/* Subtle pattern */}
      <div className="absolute inset-0 opacity-[0.03]">
        <div
          className="h-full w-full"
          style={{
            backgroundImage:
              "repeating-linear-gradient(90deg, currentColor 0px, currentColor 1px, transparent 1px, transparent 60px), repeating-linear-gradient(0deg, currentColor 0px, currentColor 1px, transparent 1px, transparent 60px)",
          }}
        />
      </div>

      <div className="relative mx-auto max-w-3xl px-6 text-center lg:px-8">
        <p
          className={`mb-3 text-sm font-semibold tracking-widest text-primary uppercase ${
            isVisible ? "animate-fade-up" : "opacity-0"
          }`}
        >
          Acceso anticipado
        </p>
        <h2
          className={`font-serif text-3xl font-bold tracking-tight text-foreground sm:text-4xl lg:text-5xl text-balance ${
            isVisible ? "animate-fade-up animation-delay-100" : "opacity-0"
          }`}
        >
          Estamos en etapa de acceso anticipado.
        </h2>
        <p
          className={`mx-auto mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground ${
            isVisible ? "animate-fade-up animation-delay-200" : "opacity-0"
          }`}
        >
          Los primeros en sumarse van a tener onboarding prioritario, precio de
          fundadores e influencia directa sobre el roadmap del producto.
        </p>

        <div
          className={`mt-10 ${
            isVisible ? "animate-fade-up animation-delay-300" : "opacity-0"
          }`}
        >
          {submitted ? (
            <div className="mx-auto flex max-w-md flex-col items-center rounded-lg border border-primary/30 bg-primary/10 p-8">
              <CheckCircle2 className="h-10 w-10 text-primary" />
              <p className="mt-4 text-lg font-semibold text-foreground">
                {"¡Estás en la lista!"}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                Te vamos a avisar apenas sea tu turno. Revisá tu email.
              </p>
            </div>
          ) : (
            <form
              onSubmit={handleSubmit}
              className="mx-auto flex max-w-lg flex-col gap-3 sm:flex-row"
            >
              <div className="relative flex-1">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value)
                    setError("")
                  }}
                  placeholder="tu@empresa.com"
                  className="w-full rounded-sm border border-border bg-background px-5 py-4 text-base text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  aria-label="Email para lista de espera"
                />
                {error && (
                  <p className="absolute -bottom-6 left-0 text-sm text-destructive">
                    {error}
                  </p>
                )}
              </div>
              <button
                type="submit"
                className="group flex shrink-0 items-center justify-center gap-2 rounded-sm bg-primary px-8 py-4 text-base font-semibold text-primary-foreground transition-all hover:brightness-110"
              >
                Reservar mi lugar
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </button>
            </form>
          )}
        </div>

        {!submitted && (
          <p
            className={`mt-8 text-sm text-muted-foreground ${
              isVisible
                ? "animate-fade-up animation-delay-400"
                : "opacity-0"
            }`}
          >
            Sin tarjeta de crédito. Sin compromiso. Te avisamos cuando es tu
            turno.
          </p>
        )}
      </div>
    </section>
  )
}
