"use client";

import { useState } from "react";
import Link from "next/link";
import { LegitScoreLogo } from "@/components/ui/legitscore-logo";
import { forgotPassword } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await forgotPassword(email.trim());
      setSent(true);
    } catch {
      setError("Wystąpił błąd. Spróbuj ponownie.");
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
              Reset hasła
            </h1>
            <p className="mt-1 text-xs text-muted-foreground">
              Wyślemy Ci link do ustawienia nowego hasła.
            </p>
          </div>
        </div>

        {sent ? (
          <div className="space-y-4">
            <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/20 px-4 py-3 text-sm text-emerald-300">
              Jeśli konto istnieje, wysłaliśmy email z linkiem do resetu hasła. Sprawdź skrzynkę.
            </div>
            <Link
              href="/login"
              className="block text-center text-xs text-slate-400 hover:text-slate-200"
            >
              ← Wróć do logowania
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl border border-border/60 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/30"
                placeholder="twoj@email.com"
              />
            </div>

            {error && (
              <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-full bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-400 disabled:opacity-60"
            >
              {loading ? "Wysyłanie..." : "Wyślij link resetu"}
            </button>

            <p className="text-center text-xs text-muted-foreground">
              <Link href="/login" className="text-slate-400 hover:text-slate-200">
                ← Wróć do logowania
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
