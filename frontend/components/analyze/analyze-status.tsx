"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getCase, runDecision, uploadAssets } from "@/lib/api";
import {
  clearPendingSubmission,
  getPendingSubmission,
} from "@/lib/submission-store";
import { Loader2, ShieldAlert } from "lucide-react";

type Props = {
  caseId?: string;
  mode?: string;
};

export function AnalyzeStatus({ caseId, mode }: Props) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!caseId) {
      setError("Brak identyfikatora sprawy w adresie URL.");
      return;
    }

    const id: string = caseId;
    let cancelled = false;

    async function runFullFlow() {
      const submission = getPendingSubmission();
      if (submission && submission.caseId === id) {
        try {
          await uploadAssets(id, submission.files);

          await runDecision(id, submission.mode);

          clearPendingSubmission();

          const qs = new URLSearchParams();
          qs.set("caseId", id);
          if (submission.mode) qs.set("mode", submission.mode);
          router.replace(`/case/${id}?${qs.toString()}`);
          return;
        } catch (e: any) {
          if (!cancelled) {
            setError(
              e instanceof Error
                ? e.message
                : "Nie udało się dokończyć analizy. Spróbuj ponownie później."
            );
          }
          clearPendingSubmission();
        }
      }
      async function pollOnce() {
        try {
          const data: any = await getCase(id);
          const status: string | undefined = data?.status;
          if (status === "DECIDED") {
            const qs = new URLSearchParams();
            qs.set("caseId", id);
            if (mode) qs.set("mode", mode);
            router.replace(`/case/${id}?${qs.toString()}`);
          } else {
            setTick((t) => t + 1);
          }
        } catch (e: any) {
          if (!cancelled) {
            setError(
              e instanceof Error
                ? e.message
                : "Nie udało się pobrać statusu sprawy."
            );
          }
        }
      }

      // Interval polling in fallback mode
      const timer = setInterval(() => {
        if (!cancelled) {
          pollOnce();
        }
      }, 2500);

      // Initial poll
      pollOnce();

      return () => {
        clearInterval(timer);
      };
    }

    runFullFlow();

    // prosty timer do rotacji komunikatów co kilka sekund
    const timer = setInterval(() => {
      if (!cancelled) {
        setTick((t) => t + 1);
      }
    }, 2500);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [caseId, mode, router]);

  const step = tick % 6;

  return (
    <div className="glass-card flex w-full max-w-md flex-col items-center justify-center gap-4 p-8 text-center">
      <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
      <div className="space-y-1">
        <h1 className="text-lg font-semibold tracking-tight text-slate-50">
          Analizujemy koszulkę
        </h1>
        <p className="text-xs text-muted-foreground">
          Sprawdzamy detale, metki i spójność wykonania. Generujemy raport
          ryzyka autentyczności.
        </p>
      </div>
      <ul className="space-y-1 text-left text-[11px] text-muted-foreground">
        <StatusLine active={step === 0}>
          Przesyłanie zdjęć...
        </StatusLine>
        <StatusLine active={step === 1}>
          Analiza elementów wizualnych...
        </StatusLine>
        <StatusLine active={step === 2}>
          Sprawdzanie zgodności modelu...
        </StatusLine>
        <StatusLine active={step === 3}>
          Porównywanie z bazą koszulek...
        </StatusLine>
        <StatusLine active={step === 4}>
          Budowanie raportu ryzyka...
        </StatusLine>
        <StatusLine active={step === 5}>
          Finalizowanie analizy...
        </StatusLine>
      </ul>
      <p className="text-[11px] text-slate-400">
        Analiza może potrwać od kilku sekund do około minuty. Produkt jest w
        wersji beta i dostarcza raport ryzyka, a nie certyfikat.
      </p>
      {error && (
        <div className="mt-2 flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200">
          <ShieldAlert className="h-3.5 w-3.5" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

function StatusLine({
  active,
  children,
}: {
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <li className="flex items-start gap-2">
      <span
        className={`mt-[3px] h-1.5 w-1.5 rounded-full ${
          active ? "bg-emerald-400" : "bg-slate-500"
        }`}
      />
      <span>{children}</span>
    </li>
  );
}

