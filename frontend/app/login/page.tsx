"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";
import { LegitScoreLogo } from "@/components/ui/legitscore-logo";
import { SocialLoginButtons } from "@/components/auth/social-login-buttons";
import { REGULAMIN_VERSION, PRIVACY_VERSION } from "@/lib/legal-versions";

// Przyciski OAuth renderują się tylko gdy te env vary są ustawione (patrz
// social-login-buttons.tsx) — checkbox zgody i separator mają się pokazywać
// dokładnie w tych samych warunkach, inaczej wisi "zgoda" bez żadnych przycisków pod nią.
const OAUTH_AVAILABLE = Boolean(
  process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || process.env.NEXT_PUBLIC_FACEBOOK_APP_ID
);

function LoginForm() {
  const { login, user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/collection";

  const [socialConsent, setSocialConsent] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user) router.replace(next);
  }, [user, next, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email.trim(), password);
      router.replace(next);
    } catch (err: any) {
      setError(err.message || "Błąd logowania.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 items-center justify-center py-10">
      <div className="glass-card w-full max-w-sm space-y-6 p-8">
        <div className="flex flex-col items-center gap-3">
          <LegitScoreLogo size={100} className="h-16 w-auto" />
          <div className="text-center">
            <h1 className="text-xl font-semibold tracking-tight text-slate-50">
              Zaloguj się do LegitScore
            </h1>
            <p className="mt-1 text-xs text-muted-foreground">
              Analizuj autentyczność koszulek i zarządzaj swoją kolekcją w jednym miejscu.
            </p>
          </div>
        </div>

        {OAUTH_AVAILABLE && (
          <>
            <div className="space-y-2">
              <label className="flex items-start gap-2 text-[11px] text-muted-foreground">
                <input
                  type="checkbox"
                  checked={socialConsent}
                  onChange={(e) => setSocialConsent(e.target.checked)}
                  className="mt-0.5 h-3.5 w-3.5 cursor-pointer rounded border-border bg-slate-950/70 text-emerald-500 outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
                />
                <span>
                  Akceptuję{" "}
                  <Link href="/regulamin" target="_blank" rel="noopener noreferrer" className="text-emerald-300 underline">
                    Regulamin
                  </Link>{" "}
                  i{" "}
                  <Link href="/polityka-prywatnosci" target="_blank" rel="noopener noreferrer" className="text-emerald-300 underline">
                    Politykę prywatności
                  </Link>{" "}
                  (dotyczy zakładania nowego konta przez Google/Facebook).
                </span>
              </label>
              <SocialLoginButtons
                consentAccepted={socialConsent}
                consent={{ regulaminVersion: REGULAMIN_VERSION, privacyVersion: PRIVACY_VERSION }}
                onError={setError}
              />
            </div>

            <div className="flex items-center gap-3 text-[10px] uppercase tracking-widest text-slate-600">
              <span className="h-px flex-1 bg-border/60" />
              albo emailem
              <span className="h-px flex-1 bg-border/60" />
            </div>
          </>
        )}

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
              value={password}
              onChange={(e) => setPassword(e.target.value)}
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
            {loading ? "Logowanie..." : "Zaloguj się"}
          </button>
        </form>

        <div className="space-y-2 text-center">
          <p className="text-xs text-muted-foreground">
            <Link href="/forgot-password" className="text-slate-400 hover:text-slate-200">
              Zapomniałeś hasła?
            </Link>
          </p>
          <p className="text-xs text-muted-foreground">
            Nie masz konta?{" "}
            <Link
              href={`/register${next !== "/collection" ? `?next=${encodeURIComponent(next)}` : ""}`}
              className="text-emerald-400 hover:underline"
            >
              Zarejestruj się
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
