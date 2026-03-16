"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getCase, runDecision, uploadAssets, importFromUrl } from "@/lib/api";
import {
  clearPendingSubmission,
  getPendingSubmission,
} from "@/lib/submission-store";
import { Loader2, ShieldAlert, AlertTriangle, ArrowLeft, Camera } from "lucide-react";

const DEBUG = typeof process !== "undefined" && process.env.NODE_ENV === "development";

type PrecheckError = {
  stage: "coverage" | "quality";
  message: string;
  missing_required?: string[];
  missing_optional?: string[];
  issues?: Array<{ area: string; issue: string }>;
  detected_views?: Record<string, boolean>;
};

type Props = {
  caseId?: string;
  mode?: string;
};

export function AnalyzeStatus({ caseId, mode }: Props) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [precheckError, setPrecheckError] = useState<PrecheckError | null>(null);
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
          if (status === "PRECHECK_FAILED") {
            stopPolling();
            // Pobierz szczegóły precheck z case data
            const precheckResult = data?.precheck_result;
            if (precheckResult && !cancelled) {
              setPrecheckError(precheckResult);
            } else if (!cancelled) {
              setError("Zdjęcia nie spełniają wymagań do analizy. Sprawdź jakość i kompletność zdjęć.");
            }
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
            } else if (submission.fileData && submission.fileData.length > 0) {
              // Odtwarzamy File objects z ArrayBuffer (bezpieczne po nawigacji iOS Safari)
              const files = submission.fileData.map(
                ({ name, type, buffer }) => new File([buffer], name, { type })
              );
              await uploadAssets(id, files);
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
            clearPendingSubmission();
            if (cancelled) return;

            // Spróbuj sparsować błąd prechecka
            const errorMessage = e instanceof Error ? e.message : String(e);

            // Sprawdź czy to błąd prechecka (zawiera stage)
            try {
              // Jeśli message wygląda jak JSON z stage, to precheck error
              if (errorMessage.includes('"stage"') || errorMessage.includes("stage")) {
                // Pobierz case data z precheck_result
                const caseData: any = await getCase(id);
                if (caseData?.precheck_result) {
                  setPrecheckError(caseData.precheck_result);
                  return;
                }
              }
            } catch {
              // Ignoruj błędy parsowania
            }

            setError(errorMessage || "Nie udało się dokończyć analizy. Spróbuj ponownie później.");
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

  const step = tick % 8;

  // UI dla błędu prechecka
  if (precheckError) {
    return (
      <div className="glass-card flex w-full max-w-lg flex-col gap-5 p-6 md:p-8">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-500/20">
            <AlertTriangle className="h-5 w-5 text-amber-400" />
          </div>
          <div className="flex-1">
            <h1 className="text-lg font-semibold text-slate-50">
              {precheckError.stage === "coverage"
                ? "Brakuje wymaganych zdjęć"
                : "Problemy z jakością zdjęć"}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {precheckError.message}
            </p>
          </div>
        </div>

        {/* Lista brakujących zdjęć (coverage) */}
        {precheckError.missing_required && precheckError.missing_required.length > 0 && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-amber-300">
              <Camera className="h-3.5 w-3.5" />
              Wymagane zdjęcia
            </div>
            <ul className="space-y-1">
              {precheckError.missing_required.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm text-amber-100">
                  <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-amber-400" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Pokaż wykryte widoki gdy missing_required jest puste */}
        {precheckError.stage === "coverage" &&
         (!precheckError.missing_required || precheckError.missing_required.length === 0) &&
         precheckError.detected_views && (
          <div className="rounded-xl border border-slate-600/50 bg-slate-800/30 p-4">
            <div className="mb-2 text-xs font-medium text-slate-400">
              Status wykrytych zdjęć:
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {Object.entries(precheckError.detected_views).map(([key, detected]) => (
                <div key={key} className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${detected ? "bg-emerald-400" : "bg-red-400"}`} />
                  <span className={detected ? "text-slate-300" : "text-red-300"}>
                    {translateViewName(key)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Lista opcjonalnych zdjęć */}
        {precheckError.missing_optional && precheckError.missing_optional.length > 0 && (
          <div className="rounded-xl border border-slate-600/50 bg-slate-800/30 p-4">
            <div className="mb-2 text-xs font-medium text-slate-400">
              Opcjonalne (zwiększą dokładność analizy):
            </div>
            <ul className="space-y-1">
              {precheckError.missing_optional.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2 text-xs text-slate-300">
                  <span className="mt-1 h-1 w-1 rounded-full bg-slate-500" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Lista problemów jakościowych */}
        {precheckError.issues && precheckError.issues.length > 0 && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-amber-300">
              <ShieldAlert className="h-3.5 w-3.5" />
              Wykryte problemy
            </div>
            <ul className="space-y-1">
              {precheckError.issues.map((issue, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm text-amber-100">
                  <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-amber-400" />
                  <span>
                    {translateIssue(issue.area, issue.issue)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-col gap-2 sm:flex-row">
          <Link
            href="/analyze/form"
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 shadow-lg shadow-emerald-500/30 transition hover:bg-emerald-400"
          >
            <Camera className="h-4 w-4" />
            Dodaj nowe zdjęcia
          </Link>
          <Link
            href="/analyze"
            className="inline-flex items-center justify-center gap-2 rounded-full border border-slate-600 px-4 py-2.5 text-sm text-slate-300 transition hover:border-slate-500 hover:text-slate-100"
          >
            <ArrowLeft className="h-4 w-4" />
            Wróć
          </Link>
        </div>
      </div>
    );
  }

  // UI dla generycznego błędu
  if (error) {
    return (
      <div className="glass-card flex w-full max-w-md flex-col items-center justify-center gap-4 p-8 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-500/20">
          <ShieldAlert className="h-6 w-6 text-red-400" />
        </div>
        <div className="space-y-1">
          <h1 className="text-lg font-semibold tracking-tight text-slate-50">
            Wystąpił błąd
          </h1>
          <p className="text-sm text-muted-foreground">{error}</p>
        </div>
        <Link
          href="/analyze/form"
          className="mt-2 inline-flex items-center justify-center gap-2 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 shadow-lg shadow-emerald-500/30 transition hover:bg-emerald-400"
        >
          Spróbuj ponownie
        </Link>
      </div>
    );
  }

  // UI dla ładowania (spinner)
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
          Sprawdzamy metki i nadruki szyjne...
        </StatusLine>
        <StatusLine active={step === 2}>
          Analizujemy haft i herb producenta...
        </StatusLine>
        <StatusLine active={step === 3}>
          Oceniamy materiał i technologię...
        </StatusLine>
        <StatusLine active={step === 4}>
          Weryfikujemy personalizację...
        </StatusLine>
        <StatusLine active={step === 5}>
          Sprawdzamy spójność wykonania...
        </StatusLine>
        <StatusLine active={step === 6}>
          Budowanie raportu ryzyka...
        </StatusLine>
        <StatusLine active={step === 7}>
          Finalizowanie analizy i generowanie PDF...
        </StatusLine>
      </ul>
      <p className="text-xs text-slate-400">
        Analiza zajmuje zwykle od 30 sekund do minuty. LegitScore dostarcza
        raport ryzyka — nie certyfikat autentyczności.
      </p>
    </div>
  );
}

function translateIssue(area: string, issue: string): string {
  const areas: Record<string, string> = {
    material_closeup: "Zdjęcie materiału",
    tag_sku: "Zdjęcie metki/SKU",
    crest_logo: "Zdjęcie herbu/logo",
    personalization: "Zdjęcie personalizacji",
    general: "Ogólnie",
  };
  const issues: Record<string, string> = {
    blur: "jest nieostre",
    too_far: "jest za daleko",
    low_light: "ma słabe oświetlenie",
    compression: "jest zbyt skompresowane",
    not_visible: "jest niewidoczne",
  };
  const areaText = areas[area] || area;
  const issueText = issues[issue] || issue;
  return `${areaText} ${issueText}`;
}

function translateViewName(key: string): string {
  const names: Record<string, string> = {
    // nowe nazwy kategorii
    front_full: "Przód koszulki (pełny)",
    back_full: "Tył koszulki (pełny)",
    crest_or_brand_closeup: "Zbliżenie herbu / logo producenta",
    identity_tag: "Metka identyfikacyjna",
    material_closeup: "Zbliżenie materiału",
    paper_sku_tag: "Metka / tag SKU",
    patch_closeup: "Naszywka",
    personalization_closeup: "Personalizacja (zbliżenie)",
    sleeve_details: "Detale rękawów",
    // kompatybilność wsteczna ze starymi raportami
    front: "Przód koszulki",
    back: "Tył koszulki",
    crest_logo_closeup: "Zbliżenie herbu/logo",
    tag_sku: "Metka/SKU",
    personalization: "Personalizacja",
    sleeve_patch: "Naszywka na rękawie",
  };
  return names[key] || key;
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

