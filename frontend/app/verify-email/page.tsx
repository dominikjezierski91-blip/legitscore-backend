"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { LegitScoreLogo } from "@/components/ui/legitscore-logo";
import { verifyEmail } from "@/lib/api";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [status, setStatus] = useState<"loading" | "success" | "error">(
    token ? "loading" : "error"
  );
  const [error, setError] = useState<string | null>(
    token ? null : "Brak tokenu weryfikacyjnego. Sprawdź link w emailu."
  );

  useEffect(() => {
    if (!token) return;
    verifyEmail(token)
      .then(() => setStatus("success"))
      .catch((err: any) => {
        setError(err.message || "Nieprawidłowy lub wygasły link.");
        setStatus("error");
      });
  }, [token]);

  return (
    <div className="flex flex-1 items-center justify-center py-10">
      <div className="glass-card w-full max-w-sm space-y-6 p-8 text-center">
        <div className="flex flex-col items-center gap-3">
          <LegitScoreLogo size={100} className="h-16 w-auto" />
          <h1 className="text-xl font-semibold tracking-tight text-slate-50">
            Potwierdzenie adresu email
          </h1>
        </div>

        {status === "loading" && (
          <p className="text-sm text-muted-foreground">Weryfikuję link…</p>
        )}

        {status === "success" && (
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
            Adres email potwierdzony. Dziękujemy!
          </div>
        )}

        {status === "error" && (
          <div className="space-y-3">
            <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">
              {error}
            </p>
            <p className="text-xs text-muted-foreground">
              Możesz poprosić o nowy link w{" "}
              <Link href="/account" className="text-emerald-300 underline">
                ustawieniach konta
              </Link>
              .
            </p>
          </div>
        )}

        <Link
          href="/collection"
          className="inline-flex items-center justify-center gap-1.5 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-400"
        >
          Przejdź do LegitScore
        </Link>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmailContent />
    </Suspense>
  );
}
