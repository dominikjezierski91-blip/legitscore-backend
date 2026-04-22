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
  const [progress, setProgress] = useState<{ stage: string; percent: number; label: string } | null>(null);
  const [simPercent, setSimPercent] = useState(5);
  const simStartRef = useRef(Date.now());

  const runDecisionStartedRef = useRef(false);
  const errorHandledRef = useRef(false);
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

      const POLL_INTERVAL_MS = 2000;

      const pollOnce = async () => {
        if (cancelled) return;
        try {
          const data: any = await getCase(id);
          if (cancelled) return;
          if (data?.progress) setProgress(data.progress);
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
            if (!cancelled && !errorHandledRef.current) {
              errorHandledRef.current = true;
              setError("Analiza zakończyła się błędem. Spróbuj ponownie później.");
            }
            return;
          }
          if (status === "PRECHECK_FAILED") {
            stopPolling();
            if (!cancelled && !errorHandledRef.current) {
              errorHandledRef.current = true;
              const precheckResult = data?.precheck_result;
              if (precheckResult) {
                setPrecheckError(precheckResult);
              } else {
                setError("Zdjęcia nie spełniają wymagań do analizy. Sprawdź jakość i kompletność zdjęć.");
              }
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

    // Polling zawsze startuje — pokazuje postęp niezależnie od runDecision
    startPolling();

    const submission = getPendingSubmission();

    if (submission && submission.caseId === id && !runDecisionStartedRef.current) {
      runDecisionStartedRef.current = true;
      if (DEBUG) console.debug("[AnalyzeStatus] runDecision started case_id=", id);
      (async () => {
        try {
          await runDecision(id, submission.mode);
          clearPendingSubmission();
          // Polling wykryje DECIDED i przekieruje — nic tu nie robimy
        } catch (e: any) {
          clearPendingSubmission();
          if (cancelled || errorHandledRef.current) return;

          try {
            const caseData: any = await getCase(id);
            if (caseData?.status === "DECIDED") return;
            if (caseData?.precheck_result) {
              errorHandledRef.current = true;
              setPrecheckError(caseData.precheck_result);
              return;
            }
          } catch {}

          errorHandledRef.current = true;
          const errorMessage = e instanceof Error ? e.message : String(e);
          setError(errorMessage || "Nie udało się dokończyć analizy. Spróbuj ponownie później.");
        }
      })();
    }

    tickIntervalRef.current = setInterval(() => {
      if (!cancelled) {
        setTick((t) => t + 1);
        const elapsed = (Date.now() - simStartRef.current) / 1000;
        // Rośnie od 5% do 90% przez ~240 sekund (krzywa log)
        const sim = Math.min(90, 5 + 85 * (1 - Math.exp(-elapsed / 80)));
        setSimPercent(Math.round(sim));
      }
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

  // UI dla ładowania (progress bar)
  const progressPercent = Math.max(simPercent, progress?.percent ?? 0);
  const currentStage = progress?.stage ?? "";

  const STAGE_LABELS: Record<string, string> = {
    starting:         "Przygotowywanie analizy...",
    coverage:         "Sprawdzanie kompletności zdjęć...",
    quality:          "Ocena jakości i ostrości zdjęć...",
    agent_a:          "Analiza forensyczna koszulki...",
    agent_a_running:  "Badanie szwów, metek i nadruków...",
    consistency:      "Weryfikacja personalizacji zawodnika...",
    sku:              "Weryfikacja kodu produktu (SKU)...",
    mfg_check:        "Ocena jakości wykonania i materiałów...",
    rule_engine:      "Obliczanie werdyktu końcowego...",
    generating:       "Generowanie raportu...",
    done:             "Analiza zakończona!",
  };
  const progressLabel = STAGE_LABELS[currentStage] ?? "Trwa analiza...";

  const STEPS = [
    { label: "Zdjęcia",   stages: ["starting", "coverage", "quality"] },
    { label: "Analiza",   stages: ["agent_a", "agent_a_running"] },
    { label: "Zawodnik",  stages: ["consistency"] },
    { label: "SKU",       stages: ["sku"] },
    { label: "Wykonanie", stages: ["mfg_check"] },
    { label: "Werdykt",   stages: ["rule_engine"] },
    { label: "Raport",    stages: ["generating", "done"] },
  ];

  const stageOrder = ["starting","coverage","quality","agent_a","agent_a_running","consistency","sku","mfg_check","rule_engine","generating","done"];
  const currentStageIdx = stageOrder.indexOf(currentStage);

  return (
    <div className="glass-card flex w-full max-w-md flex-col gap-6 p-8">
      <div className="flex items-center gap-3">
        <Loader2 className="h-5 w-5 animate-spin text-emerald-400 shrink-0" />
        <h1 className="text-lg font-semibold tracking-tight text-slate-50">
          Analizujemy koszulkę
        </h1>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-300 font-medium">{progressLabel}</span>
          <span className="text-emerald-400 font-bold">{progressPercent}%</span>
        </div>
        <div className="relative w-full h-3 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-700 ease-out"
            style={{ width: `${progressPercent}%` }}
          />
          {progressPercent > 0 && progressPercent < 100 && (
            <div
              className="absolute inset-y-0 rounded-full bg-white/20 animate-pulse"
              style={{ width: `${progressPercent}%` }}
            />
          )}
        </div>
        <div className="grid grid-cols-7 gap-1 mt-2">
          {STEPS.map((step) => {
            const lastStageIdx = stageOrder.indexOf(step.stages[step.stages.length - 1]);
            const firstStageIdx = stageOrder.indexOf(step.stages[0]);
            const isDone = currentStageIdx > lastStageIdx && currentStage !== "";
            const isActive = step.stages.includes(currentStage);
            return (
              <div key={step.label} className="flex flex-col items-center gap-1">
                <div className={`w-2 h-2 rounded-full transition-all duration-500 ${
                  isDone ? "bg-emerald-400 scale-110"
                  : isActive ? "bg-emerald-400 scale-125 ring-2 ring-emerald-400/40"
                  : "bg-slate-600"
                }`} />
                <span className={`text-[9px] text-center leading-tight ${
                  isDone || isActive ? "text-emerald-400" : "text-slate-500"
                }`}>
                  {step.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <p className="text-xs text-slate-400 text-center">
        Analiza zajmuje zwykle 3–4 minuty. LegitScore dostarcza
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
    paper_sku_tag: "Metka z kodem SKU",
    patch_closeup: "Zbliżenie naszywek",
    personalization_closeup: "Zdjęcie personalizacji (zbliżenie)",
    sleeve_details: "Szczegóły rękawa",
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

