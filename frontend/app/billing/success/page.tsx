"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getCredits } from "@/lib/api";
import { getPendingSubmission } from "@/lib/submission-store";
import { CheckCircle2, Loader2 } from "lucide-react";

// Stripe może dostarczyć webhook (checkout.session.completed) z niewielkim opóźnieniem
// względem przekierowania usera na tę stronę — dopytujemy saldo kilka razy zamiast
// pokazać stare kredyty od razu.
const POLL_ATTEMPTS = 5;
const POLL_INTERVAL_MS = 1500;

export default function BillingSuccessPage() {
  const router = useRouter();
  const [credits, setCredits] = useState<number | null>(null);
  const [checking, setChecking] = useState(true);
  const [resuming, setResuming] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let initialCredits: number | null = null;

    async function poll() {
      for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt++) {
        if (cancelled) return;
        try {
          const res = await getCredits();
          if (attempt === 0) initialCredits = res.credits;
          if (cancelled) return;
          setCredits(res.credits);
          if (initialCredits !== null && res.credits > initialCredits) {
            setChecking(false);
            maybeResume();
            return;
          }
        } catch {
          // ignoruj pojedynczy błąd, spróbuj ponownie
        }
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      }
      if (!cancelled) setChecking(false);
    }

    // Jeśli user trafił tu z ekranu "brak kredytów" w trakcie analizy, zdjęcia są
    // już wgrane pod tamtym case_id (patrz analyze-status.tsx — celowo nie czyści
    // pendingSubmission przy 402). Nie ma sensu każenie mu wgrywać ich drugi raz —
    // wracamy prosto do dokończenia tej samej analizy.
    function maybeResume() {
      const pending = getPendingSubmission();
      if (pending) {
        setResuming(true);
        setTimeout(() => {
          router.replace(`/analyze/status?case_id=${pending.caseId}&mode=${pending.mode}`);
        }, 1200);
      }
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 py-16 text-center">
      <div className="glass-card flex max-w-sm flex-col items-center gap-4 p-8">
        {checking || resuming ? (
          <Loader2 className="h-10 w-10 animate-spin text-emerald-400" />
        ) : (
          <CheckCircle2 className="h-10 w-10 text-emerald-400" />
        )}
        <div>
          <p className="text-lg font-semibold text-slate-50">
            {checking
              ? "Potwierdzamy płatność..."
              : resuming
              ? "Wznawiamy Twoją analizę..."
              : "Płatność zaakceptowana"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {resuming
              ? "Zdjęcia masz już wgrane — nie musisz przesyłać ich ponownie."
              : credits !== null
              ? `Dostępne kredyty: ${credits}`
              : "Za chwilę zobaczysz doliczone kredyty."}
          </p>
        </div>
        {!resuming && (
          <>
            <Link
              href="/analyze/form"
              className="mt-1 inline-flex items-center justify-center gap-1.5 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-400"
            >
              Sprawdź koszulkę
            </Link>
            <Link href="/account" className="text-xs text-muted-foreground underline underline-offset-2">
              Wróć do konta
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
