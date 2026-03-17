"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";
import { ProfileSurveyModal } from "@/components/onboarding/profile-survey-modal";
import { LegitScoreLogo } from "@/components/ui/legitscore-logo";

export default function RegisterPage() {
  const { register, user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/collection";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showSurvey, setShowSurvey] = useState(false);

  useEffect(() => {
    // Tylko dla już zalogowanych przed wypełnieniem formularza
    if (user && !showSurvey) router.replace(next);
  }, [user, next, router, showSurvey]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== passwordConfirm) {
      setError("Hasła nie są identyczne.");
      return;
    }
    setLoading(true);
    try {
      await register(email.trim(), password, passwordConfirm);
      // Konto utworzone — pokaż opcjonalny krok profilowania
      setShowSurvey(true);
    } catch (err: any) {
      setError(err.message || "Błąd rejestracji.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {showSurvey && (
        <ProfileSurveyModal onDone={() => router.replace(next)} />
      )}

      <div className="flex flex-1 items-center justify-center py-10">
        <div className="glass-card w-full max-w-sm space-y-6 p-8">
          <div className="flex flex-col items-center gap-3">
            <LegitScoreLogo size={100} className="h-16 w-auto" />
            <div className="text-center">
              <h1 className="text-xl font-semibold tracking-tight text-slate-50">
                Załóż konto
              </h1>
              <p className="mt-1 text-xs text-muted-foreground">
                Zapisuj sprawdzone koszulki i buduj swoją kolekcję w LegitScore.
              </p>
            </div>
          </div>

          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 space-y-1.5">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mb-2">Dlaczego warto?</p>
            <ul className="space-y-1.5 text-xs text-slate-300">
              <li className="flex items-center gap-2">
                <span className="text-emerald-400 font-semibold">✓</span>
                Analiza autentyczności koszulek AI
              </li>
              <li className="flex items-center gap-2">
                <span className="text-emerald-400 font-semibold">✓</span>
                Zarządzaj swoją kolekcją
              </li>
              <li className="flex items-center gap-2">
                <span className="text-emerald-400 font-semibold">✓</span>
                Śledź wartość swoich koszulek
              </li>
            </ul>
          </div>

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
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300">Hasło</label>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-border/60 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/30"
                placeholder="min. 8 znaków"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300">Powtórz hasło</label>
              <input
                type="password"
                required
                value={passwordConfirm}
                onChange={(e) => setPasswordConfirm(e.target.value)}
                className="w-full rounded-xl border border-border/60 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/30"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-full bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-400 disabled:opacity-60"
            >
              {loading ? "Tworzenie konta..." : "Załóż konto"}
            </button>
          </form>

          <p className="text-center text-xs text-muted-foreground">
            Masz już konto?{" "}
            <Link href={`/login${next !== "/collection" ? `?next=${encodeURIComponent(next)}` : ""}`} className="text-emerald-400 hover:underline">
              Zaloguj się
            </Link>
          </p>

          <p className="text-center text-[10px] text-slate-600">
            Nie wysyłamy spamu. Możesz usunąć konto w dowolnym momencie.
            Dane analizowanych zdjęć nie są przechowywane po zakończeniu analizy.
          </p>
        </div>
      </div>
    </>
  );
}
