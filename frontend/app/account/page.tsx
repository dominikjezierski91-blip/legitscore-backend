"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";
import { getCollection } from "@/lib/api";
import { Loader2, User, LogOut, Archive, ChevronRight } from "lucide-react";

function pluralItems(n: number) {
  if (n === 1) return "1 koszulka";
  if (n >= 2 && n <= 4) return `${n} koszulki`;
  return `${n} koszulek`;
}

export default function AccountPage() {
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();
  const [itemCount, setItemCount] = useState<number | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace("/login?next=/account"); return; }
    getCollection()
      .then((items) => setItemCount(items.length))
      .catch(() => setItemCount(0));
  }, [user, authLoading, router]);

  const handleLogout = () => {
    logout();
    router.replace("/analyze");
  };

  if (authLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex flex-1 flex-col gap-6 py-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-50">Moje konto</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">Informacje o koncie i kolekcji</p>
      </div>

      {/* Profil */}
      <div className="glass-card p-5 space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
            <User className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-100">{user.email}</p>
            <p className="text-[11px] text-muted-foreground">Konto LegitScore</p>
          </div>
        </div>

        <div className="border-t border-border/40 pt-3">
          <Link
            href="/collection"
            className="flex items-center justify-between rounded-lg px-1 py-2 text-sm text-slate-300 transition hover:text-slate-100"
          >
            <span className="flex items-center gap-2">
              <Archive className="h-4 w-4 text-slate-500" />
              Moja kolekcja
            </span>
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              {itemCount === null ? "…" : pluralItems(itemCount)}
              <ChevronRight className="h-3.5 w-3.5" />
            </span>
          </Link>
        </div>
      </div>

      {/* Akcje */}
      <div className="glass-card p-5 space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Akcje</p>
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-2 rounded-lg px-1 py-2 text-sm text-slate-400 transition hover:text-red-400"
        >
          <LogOut className="h-4 w-4" />
          Wyloguj się
        </button>
      </div>
    </div>
  );
}
