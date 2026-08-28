"use client";

import { ReactNode, useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bug, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/components/auth/auth-provider";
import { LegitScoreLogo } from "@/components/ui/legitscore-logo";
import { useCookieConsent } from "@/components/layout/cookie-consent-provider";
import { authHeaders } from "@/lib/auth";
import { getCredits } from "@/lib/api";

type ShellProps = {
  children: ReactNode;
  className?: string;
  subtitle?: string;
};

export function Shell({ children, className, subtitle }: ShellProps) {
  const { user } = useAuth();
  const pathname = usePathname();
  // Strona /przyklad jest publiczną wizytówką linkowaną z landing page'a (Lovable) —
  // dopóki oba serwisy nie są ze sobą spięte, odwiedzający nie powinien mieć stąd
  // furtki do wejścia w aplikację (analiza/logowanie) z pominięciem landing page'a.
  const isPublicExample = pathname?.startsWith("/przyklad") ?? false;
  const { openSettings } = useCookieConsent();
  const [criticalCount, setCriticalCount] = useState(0);
  const [credits, setCredits] = useState<number | null>(null);

  useEffect(() => {
    if (!user?.is_admin) return;
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
    fetch(`${apiBase}/api/monitoring/tickets`, { headers: authHeaders() })
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d) setCriticalCount(d.critical_count ?? 0); })
      .catch(() => {});
  }, [user]);

  useEffect(() => {
    if (!user) {
      setCredits(null);
      return;
    }
    getCredits()
      .then((res) => setCredits(res.credits))
      .catch(() => setCredits(null));
  }, [user]);

  return (
    <div className="min-h-screen gradient-bg">
      <div className="mx-auto flex min-h-screen max-w-4xl flex-col px-4 py-6 md:px-6 lg:px-8">
        <header className="mb-8 space-y-3">
          {/* Rząd 1: tożsamość + odznaki — zawsze krótki, praktycznie nigdy się nie zawija */}
          <div className="flex flex-wrap items-center justify-between gap-y-2">
            <div className="flex items-center gap-2">
              <a href="https://legitscore.app" className="flex items-center">
                <LegitScoreLogo size={80} className="h-6 w-auto md:h-7" />
              </a>
              <Badge className="border-emerald-400/40 bg-emerald-500/10 text-emerald-300">
                BETA
              </Badge>
            </div>
            <div className="flex items-center gap-3 text-xs">
              {subtitle ? (
                <span className="text-muted-foreground">{subtitle}</span>
              ) : null}
              {user && credits !== null && (
                <Link
                  href="/billing"
                  title="Dostępne analizy — kliknij, żeby dokupić"
                  className="flex items-center gap-1 rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2.5 py-1 text-emerald-300 transition hover:bg-emerald-500/20"
                >
                  <Sparkles className="h-3 w-3" />
                  Dostępne analizy: {credits}
                </Link>
              )}
              {criticalCount > 0 && (
                <Link
                  href="/dashboard#monitoring"
                  title={`${criticalCount} CRITICAL ticket${criticalCount > 1 ? "y" : ""}`}
                  className="relative text-red-400 transition hover:text-red-300"
                >
                  <Bug className="h-4 w-4" />
                  <span className="absolute -right-1 -top-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white">
                    {criticalCount}
                  </span>
                </Link>
              )}
            </div>
          </div>

          {/* Rząd 2: linki nawigacji — osobny wiersz, zawija się niezależnie od odznak powyżej */}
          <nav className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
            {user ? (
              <>
                <Link href="/analyze/form" className="text-slate-400 transition hover:text-slate-200">
                  Analiza
                </Link>
                <Link href="/historia" className="text-slate-400 transition hover:text-slate-200">
                  Historia
                </Link>
                <Link href="/collection" className="text-slate-400 transition hover:text-slate-200">
                  Kolekcja
                </Link>
                <Link href="/contact" className="text-slate-400 transition hover:text-slate-200">
                  Kontakt
                </Link>
                <Link href="/account" className="text-slate-400 transition hover:text-slate-200">
                  Konto
                </Link>
                {user.is_admin && (
                  <Link href="/dashboard" className="text-slate-400 transition hover:text-slate-200">
                    Dashboard
                  </Link>
                )}
              </>
            ) : (
              <>
                {!isPublicExample && (
                  <Link href="/analyze" className="text-slate-400 transition hover:text-slate-200">
                    Analiza
                  </Link>
                )}
                <Link href="/contact" className="text-slate-400 transition hover:text-slate-200">
                  Kontakt
                </Link>
                {!isPublicExample && (
                  <Link href="/login" className="text-slate-400 transition hover:text-slate-200">
                    Zaloguj się
                  </Link>
                )}
              </>
            )}
          </nav>
        </header>

        <main className={cn("flex flex-1 flex-col", className)}>{children}</main>

        <footer className="mt-10 border-t border-border/60 pt-4 text-center text-[10px] text-muted-foreground/70">
          <nav className="mb-2 flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
            <Link href="/regulamin" className="transition hover:text-slate-300">
              Regulamin
            </Link>
            <span aria-hidden="true">·</span>
            <Link href="/polityka-prywatnosci" className="transition hover:text-slate-300">
              Polityka prywatności
            </Link>
            <span aria-hidden="true">·</span>
            <button onClick={openSettings} className="transition hover:text-slate-300">
              Ustawienia cookies
            </button>
            <span aria-hidden="true">·</span>
            <a href="mailto:info@legitscore.app" className="transition hover:text-slate-300">
              info@legitscore.app
            </a>
          </nav>
          <p>© 2026 LegitScore. Wszystkie prawa zastrzeżone.</p>
          <p className="mt-1">
            LegitScore dostarcza analizy ryzyka autentyczności koszulek
            piłkarskich. Raport nie stanowi certyfikatu ani gwarancji.
          </p>
        </footer>
      </div>
    </div>
  );
}
