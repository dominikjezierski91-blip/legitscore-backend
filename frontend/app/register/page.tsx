"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";

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

  useEffect(() => {
    if (user) router.replace(next);
  }, [user, next, router]);

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
      router.replace(next);
    } catch (err: any) {
      setError(err.message || "Błąd rejestracji.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 items-center justify-center py-10">
      <div className="glass-card w-full max-w-sm space-y-6 p-8">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-50">
            Załóż konto
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Zapisuj sprawdzone koszulki i buduj swoją kolekcję w LegitScore.
          </p>
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
      </div>
    </div>
  );
}
