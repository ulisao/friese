"use client"

import { useState, FormEvent } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { CheckCircle2 } from "lucide-react"

export function WaitlistSection() {
  const [company, setCompany] = useState("")
  const [email, setEmail] = useState("")
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState("")
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError("")

    if (!company || !email) {
      setError("Por favor, completá ambos campos.")
      return
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email)) {
      setError("Ingresá un email válido.")
      return
    }

    setIsLoading(true)

    const FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeLOrlEBOWXWiN_8IPjSQOBppSqH9d_SbfXDgqs68xyAZYr4g/formResponse"
    
    const formData = new URLSearchParams()
    formData.append("entry.1522934148", company)
    formData.append("entry.2106078397", email)

    try {
      await fetch(FORM_URL, {
        method: "POST",
        mode: "no-cors",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: formData.toString(),
      })

      setSubmitted(true)
    } catch (err) {
      console.error(err)
      setError("Hubo un problema al procesar tu solicitud. Intentá de nuevo.")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    // Cambiamos bg-primary por bg-muted/30 para separarlo del resto sin ser tan invasivo
    <section 
    id="waitlist"
    className="py-24 bg-muted/30 flex justify-center w-full border-y border-border/50">
      <div className="container mx-auto px-4 md:px-6 text-center">
        <div className="max-w-2xl mx-auto space-y-8 flex flex-col items-center">
          <div className="space-y-4 w-full">
            {/* Texto adaptado a los colores base */}
            <h2 className="text-3xl md:text-4xl font-bold tracking-tighter text-foreground">
              ¿Listo para transformar tu forma de trabajar?
            </h2>
            <p className="text-muted-foreground md:text-xl">
              Unite a nuestra lista de espera y sé de los primeros en probar la plataforma.
            </p>
          </div>

          {submitted ? (
            /* Tarjeta de éxito con estilo "card" para máximo contraste */
            <div className="flex flex-col items-center justify-center w-full max-w-md mx-auto space-y-4 p-8 bg-card border border-border shadow-sm rounded-2xl">
              <CheckCircle2 className="w-12 h-12 text-primary" />
              <h3 className="text-2xl font-bold text-foreground">¡Gracias por sumarte!</h3>
              <p className="text-muted-foreground">
                Anotamos a <span className="font-semibold text-foreground">{company}</span>. Te vamos a avisar a <span className="font-semibold text-foreground">{email}</span> cuando estemos listos.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4 w-full max-w-md mx-auto p-6 md:p-8 bg-card border border-border shadow-sm rounded-2xl">
              <div className="space-y-4">
                {/* Inputs usando los colores base que ya tenés en ui/input.tsx */}
                <Input
                  type="text"
                  placeholder="Nombre de la empresa"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  className="bg-background border-input text-foreground h-12"
                  disabled={isLoading}
                />
                <Input
                  type="email"
                  placeholder="Tu correo electrónico"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="bg-background border-input text-foreground h-12"
                  disabled={isLoading}
                />
              </div>
              
              {error && <p className="text-destructive text-sm font-medium">{error}</p>}
              
              <Button 
                type="submit" 
                size="lg" 
                variant="default" // Volvemos al botón primario por defecto
                className="w-full mt-2"
                disabled={isLoading}
              >
                {isLoading ? "Enviando..." : "Unirme a la lista de espera"}
              </Button>
            </form>
          )}
        </div>
      </div>
    </section>
  )
}