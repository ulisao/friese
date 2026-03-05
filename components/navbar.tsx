"use client"

import { useState } from "react"
import Link from "next/link"
import { Menu, X } from "lucide-react"

export function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false)

  const scrollToWaitlist = () => {
    setMobileOpen(false)
    document.getElementById("waitlist")?.scrollIntoView({ behavior: "smooth" })
  }

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 lg:px-8">
        <Link href="/" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-sm bg-primary">
            <span className="text-sm font-bold text-primary-foreground">D</span>
          </div>
          <span className="text-lg font-semibold tracking-tight text-foreground">
            DespachoApp
          </span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden items-center gap-8 md:flex">
          <a
            href="#problema"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Problema
          </a>
          <a
            href="#plataforma"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Plataforma
          </a>
          <a
            href="#como-funciona"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Funcionamiento
          </a>
          <button
            onClick={scrollToWaitlist}
            className="rounded-sm bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-all hover:brightness-110"
          >
            Reservar mi lugar
          </button>
        </div>

        {/* Mobile toggle */}
        <button
          className="md:hidden text-foreground"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label={mobileOpen ? "Cerrar menú" : "Abrir menú"}
        >
          {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="border-t border-border/50 bg-background px-6 py-6 md:hidden">
          <div className="flex flex-col gap-4">
            <a
              href="#problema"
              onClick={() => setMobileOpen(false)}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              Problema
            </a>
            <a
              href="#plataforma"
              onClick={() => setMobileOpen(false)}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              Plataforma
            </a>
            <a
              href="#como-funciona"
              onClick={() => setMobileOpen(false)}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              Funcionamiento
            </a>
            <button
              onClick={scrollToWaitlist}
              className="mt-2 rounded-sm bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-all hover:brightness-110"
            >
              Reservar mi lugar
            </button>
          </div>
        </div>
      )}
    </nav>
  )
}
