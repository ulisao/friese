"use client"

export function Footer() {
  const scrollToWaitlist = () => {
    document.getElementById("waitlist")?.scrollIntoView({ behavior: "smooth" })
  }

  return (
    <footer className="border-t border-border/50 py-12">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="flex flex-col items-start justify-between gap-8 md:flex-row md:items-center">
          {/* Left */}
          <div>
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-sm bg-primary">
                <span className="text-xs font-bold text-primary-foreground">
                  D
                </span>
              </div>
              <span className="text-base font-semibold text-foreground">
                Friese
              </span>
            </div>
            <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted-foreground">
              Inteligencia logística para empresas que no pueden permitirse
              perder.
            </p>
          </div>

          {/* Links */}
          <div className="flex flex-wrap items-center gap-6 text-sm text-muted-foreground">
            <a href="#" className="transition-colors hover:text-foreground">
              {"Política de privacidad"}
            </a>
            <a
              href="mailto:hola@despachoapp.com"
              className="transition-colors hover:text-foreground"
            >
              Contacto
            </a>
            <button
              onClick={scrollToWaitlist}
              className="text-primary transition-colors hover:text-primary/80"
            >
              Unirse a la lista de espera
            </button>
          </div>
        </div>

        <div className="mt-10 border-t border-border/50 pt-6">
          <p className="text-xs text-muted-foreground">
            {"© 2026 Friese. Todos los derechos reservados."}
          </p>
        </div>
      </div>
    </footer>
  )
}
