"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Sparkles, Settings, Mail, LogOut, LayoutDashboard } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";

type UserMenuProps = {
  email: string;
  credits: number | null;
  isAdmin: boolean;
  criticalCount: number;
};

/** Avatar z inicjałem (na razie bez uploadu zdjęcia — to osobny, większy krok:
 * storage + endpoint + pole avatar_url na koncie) rozwijający dropdown ze
 * wszystkim, co wcześniej wisiało osobno w nagłówku (kredyty, konto, kontakt,
 * dashboard, wylogowanie) — zdejmuje to z głównego rzędu nawigacji. */
export function UserMenu({ email, credits, isAdmin, criticalCount }: UserMenuProps) {
  const { logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function handleLogout() {
    setOpen(false);
    logout();
    router.replace("/analyze");
  }

  const initial = email.charAt(0).toUpperCase();

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500/20 text-sm font-semibold text-emerald-300 ring-1 ring-emerald-400/40 transition hover:ring-emerald-400/70"
        aria-label="Konto"
      >
        {initial}
        {criticalCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white">
            {criticalCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-20 mt-2 w-56 space-y-1 rounded-2xl border border-border/60 bg-slate-900/95 p-2 text-sm shadow-xl shadow-black/40 backdrop-blur">
          <p className="truncate px-3 py-1.5 text-xs text-slate-500">{email}</p>

          {credits !== null && (
            <div className="flex items-center gap-2 rounded-xl px-3 py-2 text-emerald-300">
              <Sparkles className="h-4 w-4 shrink-0" />
              Dostępne analizy: {credits}
            </div>
          )}

          <Link
            href="/account"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-xl px-3 py-2 text-slate-300 transition hover:bg-slate-800/70 hover:text-slate-100"
          >
            <Settings className="h-4 w-4 shrink-0" />
            Konto
          </Link>

          <Link
            href="/contact"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-xl px-3 py-2 text-slate-300 transition hover:bg-slate-800/70 hover:text-slate-100"
          >
            <Mail className="h-4 w-4 shrink-0" />
            Kontakt
          </Link>

          {isAdmin && (
            <Link
              href="/dashboard"
              onClick={() => setOpen(false)}
              className="flex items-center justify-between gap-2 rounded-xl px-3 py-2 text-slate-300 transition hover:bg-slate-800/70 hover:text-slate-100"
            >
              <span className="flex items-center gap-2">
                <LayoutDashboard className="h-4 w-4 shrink-0" />
                Dashboard
              </span>
              {criticalCount > 0 && (
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
                  {criticalCount}
                </span>
              )}
            </Link>
          )}

          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-red-400 transition hover:bg-red-500/10"
          >
            <LogOut className="h-4 w-4 shrink-0" />
            Wyloguj
          </button>
        </div>
      )}
    </div>
  );
}
