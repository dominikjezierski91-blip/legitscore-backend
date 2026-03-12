import { redirect } from "next/navigation";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { FeedbackButtons } from "@/components/feedback/feedback-buttons";
import { RatingBalls } from "@/components/feedback/rating-balls";

export const dynamic = "force-dynamic";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

type Props = {
  params: { case_id: string };
  searchParams: { mode?: string };
};

export default async function CasePage({ params, searchParams }: Props) {
  const { case_id } = params;
  if (!API_BASE_URL) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="glass-card max-w-md p-6 text-sm text-amber-200">
          Brak konfiguracji NEXT_PUBLIC_API_BASE_URL. Frontend nie może
          połączyć się z backendem.
        </div>
      </div>
    );
  }

  let caseData: any;
  try {
    const res = await fetch(
      `${API_BASE_URL.replace(/\/$/, "")}/api/cases/${case_id}`,
      { cache: "no-store" }
    );
    if (!res.ok) {
      throw new Error(`Status HTTP ${res.status}`);
    }
    caseData = await res.json();
  } catch (e) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="glass-card max-w-md p-6 text-sm text-amber-200">
          Nie udało się pobrać danych sprawy. Upewnij się, że ID jest poprawne,
          a backend działa.
        </div>
      </div>
    );
  }

  const status: string | undefined = caseData?.status;
  if (status !== "DECIDED") {
    const qs = new URLSearchParams();
    qs.set("case_id", case_id);
    if (searchParams.mode) qs.set("mode", searchParams.mode);
    redirect(`/analyze/status?${qs.toString()}`);
  }

  // Spróbuj pobrać REPORT_DATA z report_data.json
  let reportData: any | null = null;
  const apiBase = API_BASE_URL.replace(/\/$/, "");
  try {
    const url = apiBase + "/api/cases/" + case_id + "/report-data";
    const res = await fetch(url, { cache: "no-store" });
    if (res.ok) {
      const wrapper = await res.json();
      if (wrapper && typeof wrapper === "object" && "REPORT_DATA" in wrapper) {
        reportData = (wrapper as any).REPORT_DATA;
      }
    }
  } catch {
    // ciche: brak raportu jest akceptowalny, pokażemy ograniczone info
  }

  const verdict = reportData?.verdict ?? {};
  const probs = reportData?.probabilities ?? {};
  const keyEvidence = (reportData?.key_evidence as any[]) || [];
  const mode = searchParams.mode;
  const reportId = reportData?.report_id as string | undefined;
  const analysisDate = reportData?.analysis_date as string | undefined;
  const cacheBust = encodeURIComponent(reportId || analysisDate || "");
  const pdfUrl =
    apiBase +
    "/api/cases/" +
    case_id +
    "/report-pdf" +
    (cacheBust ? `?v=${cacheBust}` : "");

  return (
    <div className="flex flex-1 flex-col gap-6 py-6 md:flex-row">
      <div className="flex-1 space-y-4">
          <section className="glass-card space-y-3 p-5 md:p-6">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h1 className="text-lg font-semibold tracking-tight text-slate-50 md:text-xl">
                  Podsumowanie analizy
                </h1>
                <p className="mt-1 text-xs text-muted-foreground">
                  LegitScore przedstawia uporządkowany raport ryzyka
                  autentyczności na podstawie przesłanych zdjęć. Nie jest to
                  certyfikat ani gwarancja.
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 text-[11px]">
              <span className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-3 py-1 font-medium text-emerald-200">
                BETA
              </span>
              <span className="rounded-full border border-border/70 bg-slate-950/60 px-3 py-1 text-slate-200">
                Raport ryzyka, nie certyfikat
              </span>
            </div>
          </section>

          <section className="glass-card grid gap-4 p-5 md:grid-cols-2 md:p-6">
            <div className="space-y-2">
              <div className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-200">
                <span>🧾</span>
                <span>Numer sprawy</span>
              </div>
              <p className="font-mono text-sm text-emerald-300">
                {case_id.slice(0, 8).toUpperCase()}
              </p>
              <p className="text-[10px] text-slate-500">
                Pełny ID: {case_id}
              </p>
              {mode && (
                <p className="text-[11px] text-muted-foreground">
                  Tryb raportu:{" "}
                  <span className="font-semibold text-slate-100">
                    {mode === "expert" ? "EXPERT" : "BASIC"}
                  </span>
                </p>
              )}
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-slate-200">
                <span>✅</span>
                <span>Status analizy</span>
              </div>
              <p className="text-sm text-emerald-300">Zakończona</p>
              <p className="text-[11px] text-muted-foreground">
                Pełny raport PDF zawiera szczegółową macierz decyzyjną i opis
                przesłanek. Poniżej widzisz skrócone podsumowanie.
              </p>
              {reportId && analysisDate && (
                <p className="text-[10px] text-slate-500">
                  Wersja:{" "}
                  <span className="font-mono">
                    {reportId.slice(0, 8)} · {analysisDate}
                  </span>
                </p>
              )}
            </div>
          </section>

          <section className="glass-card space-y-3 p-5 md:p-6">
            <div className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-slate-200">
              <span>📊</span>
              <span>Poziom pewności</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-3xl font-bold text-emerald-300">
                {verdict.confidence_percent ?? "—"}%
              </span>
              <span
                className={cn(
                  "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold",
                  getConfidenceBadgeClasses(verdict.confidence_level)
                )}
              >
                {getConfidenceLabel(verdict.confidence_level)}
              </span>
            </div>
          </section>

          {probs && typeof probs === "object" && Object.keys(probs).length > 0 && (
            <section className="glass-card space-y-3 p-5 md:p-6">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-200">
                Rozkład kategorii (skrót)
              </div>
              <div className="space-y-2 text-xs text-muted-foreground">
                {Object.entries(probs).map(([key, value]) => {
                  const pct = Number(value) || 0;
                  const { barColor, label } = getProbabilityBarStyle(pct, key);
                  return (
                    <div key={key} className="space-y-1">
                      <div className="flex justify-between">
                        <span className="capitalize text-slate-300">
                          {label}
                        </span>
                        <span className="text-slate-100">{pct}%</span>
                      </div>
                      <div className="h-2 w-full rounded-full bg-slate-800/60">
                        <div
                          className={cn(
                            "h-2 rounded-full transition-all",
                            barColor
                          )}
                          style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          <section className="glass-card space-y-3 p-5 md:p-6">
            <div className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-slate-200">
              <span>🔎</span>
              <span>Kluczowe sygnały (skrót)</span>
            </div>
            {keyEvidence.length > 0 ? (
              <ul className="space-y-1 text-xs text-muted-foreground">
                {keyEvidence.slice(0, 5).map((ev, idx) => {
                  const text =
                    typeof ev === "string"
                      ? ev
                      : (ev && typeof ev === "object" && "text" in ev
                          ? (ev as any).text
                          : JSON.stringify(ev));
                  return (
                    <li key={idx} className="flex gap-2">
                      <span className="mt-[3px] h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      <span>{text}</span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">
                Raport nie zawiera jawnej listy kluczowych sygnałów. Sprawdź
                pełny PDF, aby zobaczyć szczegóły analizy.
              </p>
            )}
          </section>

          <section className="glass-card space-y-3 p-5 md:p-6">
            <FeedbackButtons caseId={case_id} />
          </section>
        </div>
        <aside className="glass-card flex w-full max-w-xs flex-col justify-between p-5 md:p-6">
          <div className="space-y-3 text-xs text-muted-foreground">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-200">
              Pełny raport PDF
            </div>
            <p>
              Pełny raport zawiera macierz decyzyjną, szczegółowy opis
              przesłanek oraz dodatkowe komentarze. To dokument pomocniczy, nie
              certyfikat autentyczności.
            </p>
            <a
              href={pdfUrl}
              rel="noopener noreferrer"
              className="mt-2 inline-flex w-full items-center justify-center rounded-full bg-emerald-500 px-4 py-2.5 text-xs font-medium text-slate-950 shadow-md shadow-emerald-500/40 transition hover:bg-emerald-400"
            >
              Pobierz pełny raport PDF
            </a>
          </div>
          <div className="mt-4 border-t border-border/40 pt-4">
            <RatingBalls caseId={case_id} />
          </div>
          <div className="mt-4 border-t border-border/40 pt-4">
            <Link
              href="/analyze/form"
              className="inline-flex w-full items-center justify-center gap-2 rounded-full border border-emerald-400/60 bg-emerald-500/10 px-4 py-2.5 text-xs font-medium text-emerald-200 transition hover:bg-emerald-500/20"
            >
              Nowa analiza
            </Link>
          </div>
          <div className="mt-4 space-y-1 text-[11px] text-muted-foreground">
            <p>
              LegitScore jest w wersji beta. Raport opisuje ryzyko na podstawie
              przesłanych zdjęć i nie stanowi gwarancji ani certyfikatu.
            </p>
          </div>
        </aside>
    </div>
  );
}

function getConfidenceBadgeClasses(level?: string) {
  const val = (level || "").toLowerCase();
  if (val === "bardzo_wysoki") {
    return "bg-emerald-500/20 text-emerald-300 border border-emerald-400/60";
  }
  if (val === "wysoki") {
    return "bg-teal-500/20 text-teal-200 border border-teal-400/60";
  }
  if (val === "sredni") {
    return "bg-amber-500/20 text-amber-200 border border-amber-400/60";
  }
  if (val === "ograniczony") {
    return "bg-red-500/20 text-red-200 border border-red-400/60";
  }
  return "bg-slate-700/40 text-slate-200 border border-slate-500/60";
}

function getConfidenceLabel(level?: string) {
  const val = (level || "").toLowerCase();
  if (val === "bardzo_wysoki") return "BARDZO WYSOKA PEWNOŚĆ";
  if (val === "wysoki") return "WYSOKA PEWNOŚĆ";
  if (val === "sredni") return "ŚREDNIA PEWNOŚĆ";
  if (val === "ograniczony") return "OGRANICZONA PEWNOŚĆ";
  return "POZIOM PEWNOŚCI";
}

function getProbabilityBarStyle(pct: number, key: string) {
  let barColor = "bg-slate-600";

  // Specjalna logika dla podróbki - czerwony pasek przy wysokiej pewności
  if (key === "podrobka") {
    if (pct > 50) {
      barColor = "bg-red-500";
    } else if (pct >= 20) {
      barColor = "bg-red-400/70";
    }
  } else {
    if (pct > 70) {
      barColor = "bg-emerald-400";
    } else if (pct >= 30) {
      barColor = "bg-amber-400";
    }
  }

  const label = key.replace(/_/g, " ");
  return { barColor, label };
}

