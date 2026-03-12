"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getCase, runDecision, uploadAssets, importFromUrl } from "@/lib/api";
import {
  clearPendingSubmission,
  getPendingSubmission,
} from "@/lib/submission-store";
import { Loader2, ShieldAlert } from "lucide-react";

const DEBUG = typeof process !== "undefined" && process.env.NODE_ENV === "development";

type Props = {
  caseId?: string;
  mode?: string;
};

export function AnalyzeStatus({ caseId, mode }: Props) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const runDecisionStartedRef = useRef(false);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const tickIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (DEBUG) console.debug("[AnalyzeStatus] mount case_id=", caseId);

    if (!caseId) {
      setError("Brak identyfikatora sprawy w adresie URL.");
      return () => {
        if (DEBUG) console.debug("[AnalyzeStatus] cleanup called (no caseId)");
      };
    }

    const id: string = caseId;
    let cancelled = false;

    const stopPolling = () => {
      if (pollingIntervalRef.current !== null) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
        if (DEBUG) console.debug("[AnalyzeStatus] polling stopped");
      }
    };

    const startPolling = () => {
      stopPolling();
      if (DEBUG) console.debug("[AnalyzeStatus] polling started");

      const POLL_INTERVAL_MS = 3000;

      const pollOnce = async () => {
        if (cancelled) return;
        try {
          const data: any = await getCase(id);
          if (cancelled) return;
          const status: string | undefined = data?.status;
          if (status === "DECIDED") {
            stopPolling();
            if (!cancelled) {
              const qs = new URLSearchParams();
              qs.set("caseId", id);
              if (mode) qs.set("mode", mode);
              router.replace(`/case/${id}?${qs.toString()}`);
            }
            return;
          }
          if (status === "ERROR") {
            stopPolling();
            if (!cancelled) setError("Analiza zakończyła się błędem. Spróbuj ponownie później.");
            return;
          }
          if (DEBUG) console.debug("[AnalyzeStatus] polling tick");
          if (!cancelled) setTick((t) => t + 1);
        } catch (e: any) {
          if (!cancelled) {
            setError(
              e instanceof Error ? e.message : "Nie udało się pobrać statusu sprawy."
            );
          }
        }
      };

      pollOnce();
      pollingIntervalRef.current = setInterval(pollOnce, POLL_INTERVAL_MS);
    };

    const submission = getPendingSubmission();

    if (submission && submission.caseId === id) {
      if (runDecisionStartedRef.current) {
        if (DEBUG) console.debug("[AnalyzeStatus] runDecision skipped because already started");
        startPolling();
      } else {
        runDecisionStartedRef.current = true;
        if (DEBUG) console.debug("[AnalyzeStatus] runDecision started case_id=", id, "inputType=", submission.inputType);
        (async () => {
          try {
            // Obsłuż dwa tryby: upload zdjęć lub import z URL
            if (submission.inputType === "url" && submission.auctionUrl) {
              await importFromUrl(id, submission.auctionUrl);
            } else if (submission.files && submission.files.length > 0) {
              await uploadAssets(id, submission.files);
            }
            await runDecision(id, submission.mode);
            clearPendingSubmission();
            if (!cancelled) {
              const qs = new URLSearchParams();
              qs.set("caseId", id);
              if (submission.mode) qs.set("mode", submission.mode);
              router.replace(`/case/${id}?${qs.toString()}`);
            }
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
        })();
      }
    } else {
      startPolling();
    }

    tickIntervalRef.current = setInterval(() => {
      if (!cancelled) setTick((t) => t + 1);
    }, 2500);

    return () => {
      cancelled = true;
      stopPolling();
      if (tickIntervalRef.current !== null) {
        clearInterval(tickIntervalRef.current);
        tickIntervalRef.current = null;
      }
      if (DEBUG) console.debug("[AnalyzeStatus] cleanup called");
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
        <p className="text-sm text-muted-foreground">
          Sprawdzamy detale, metki i spójność wykonania. Generujemy raport
          ryzyka autentyczności.
        </p>
      </div>
      <ul className="space-y-1 text-left text-xs text-muted-foreground">
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
      <p className="text-xs text-slate-400">
        Analiza może potrwać od kilku sekund do około minuty. Produkt jest w
        wersji beta i dostarcza raport ryzyka, a nie certyfikat.
      </p>
      {error && (
        <div className="mt-2 flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
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

