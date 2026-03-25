"use client";

import { useState, useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { LegitScoreLogo } from "@/components/ui/legitscore-logo";
import { resetPassword } from "@/lib/api";

export default function ResetPasswordPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token") ?? "";

  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) setError("Brak tokenu resetu hasła. Sprawdź link w emailu.");
  }, [token]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPw !== confirmPw) {
      setError("Hasła nie są identyczne.");
      return;
    }
    if (newPw.length < 8) {
      setError("Hasło musi mieć co najmniej 8 znaków.");
      return;
    }
    setLoading(true);
    try {
      await resetPassword(token, newPw);
      setSuccess(true);
      setTimeout(() => router.replace("/login"), 3000);
    } catch (err: any) {
      setError(err.message || "Nieprawidłowy lub wygasły link. Poproś o nowy reset hasła.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center py-10">
      <div className="glass-card w-full max-w-sm space-y-6 p-8">
        <div className="flex flex-col items-center gap-3">
          <LegitScoreLogo size={100} className="h-16 w-auto" />
          <div className="text-center">
            <h1 className="text-xl font-semibold tracking-tight text-slate-50">
              Nowe hasło
            </h1>
            <p className="mt-1 text-xs text-muted-foreground">
              Ustaw nowe hasło do swojego konta.
            </p>
          </div>
        </div>

        {success ? (
          <div className="space-y-4">
            <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/20 px-4 py-3 text-sm text-emerald-300">
              Hasło zostało zmienione. Za chwilę zostaniesz przekierowany do logowania…
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300">Nowe hasło</label>
              <input
                type="password"
                required
                value={newPw}
                onChange={(e) => { setNewPw(e.target.value); setError(null); }}
                className="w-full rounded-xl border border-border/60 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/30"
                placeholder="Min. 8 znaków"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300">Powtórz hasło</label>
              <input
                type="password"
                required
                value={confirmPw}
                onChange={(e) => { setConfirmPw(e.target.value); setError(null); }}
                className="w-full rounded-xl border border-border/60 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/30"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading || !token}
              className="w-full rounded-full bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-400 disabled:opacity-60"
            >
              {loading ? "Zapisywanie..." : "Ustaw nowe hasło"}
            </button>

            <p className="text-center text-xs text-muted-foreground">
              <Link href="/forgot-password" className="text-slate-400 hover:text-slate-200">
                Wyślij nowy link reset
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
