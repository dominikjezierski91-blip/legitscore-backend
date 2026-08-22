"use client";

import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock,
  ImageIcon,
  Link2,
  Mail,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { ReportType } from "./report-type-selector";
import { SubmissionDisclaimer } from "./submission-disclaimer";
import { cn } from "@/lib/utils";

type Props = {
  reportType: ReportType;
  inputMode: "photos" | "url";
  imageCount: number;
  minImages: number;
  auctionUrl: string;
  isValidUrl: boolean;
  email: string;
  canSubmit: boolean;
  onSubmit: () => void;
  submitting: boolean;
  submitPhase?: "idle" | "creating" | "uploading" | "navigating";
  isLoggedIn?: boolean;
  credits?: number | null;
  disclaimerAccepted: boolean;
  onDisclaimerChange: (accepted: boolean) => void;
  showDisclaimerCheckbox: boolean;
};

export function SubmitSummaryCard({
  reportType,
  inputMode,
  imageCount,
  minImages,
  auctionUrl,
  isValidUrl,
  email,
  canSubmit,
  onSubmit,
  submitting,
  submitPhase = "idle",
  isLoggedIn = false,
  credits = null,
  disclaimerAccepted,
  onDisclaimerChange,
  showDisclaimerCheckbox,
}: Props) {
  const submitLabel =
    submitPhase === "creating" ? "Tworzę sprawę..." :
    submitPhase === "uploading" ? (inputMode === "url" ? "Pobieranie zdjęć..." : "Przesyłanie zdjęć...") :
    submitPhase === "navigating" ? "Przekierowuję..." :
    "Uruchom analizę";
  return (
    <aside className="min-w-0 rounded-2xl shadow-[0_18px_45px_rgba(16,185,129,0.25)] md:sticky md:top-6 md:self-start">
      <div className="flex h-full flex-col justify-between overflow-hidden rounded-2xl border border-emerald-500/20 bg-slate-900/70 p-5 backdrop-blur">
      <div className="space-y-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-100">
          <ShieldCheck className="h-3.5 w-3.5 text-emerald-300" />
          Podsumowanie zgłoszenia
        </div>
        <div className="space-y-2 rounded-xl border border-border/70 bg-slate-950/40 p-3">
          <SummaryRow
            icon={<Clock className="h-3 w-3" />}
            label="Typ raportu"
            value={reportType === "basic" ? "BASIC" : "EXPERT"}
            accent
          />
          {inputMode === "photos" ? (
            <SummaryRow
              icon={<ImageIcon className="h-3 w-3" />}
              label="Zdjęcia"
              value={
                imageCount >= minImages
                  ? `${imageCount} z ${minImages}+ gotowe`
                  : `${imageCount} z ${minImages} wymaganych`
              }
              status={imageCount >= minImages ? "ok" : "warn"}
            />
          ) : (
            <SummaryRow
              icon={<Link2 className="h-3 w-3" />}
              label="Link aukcji"
              value={
                auctionUrl
                  ? isValidUrl
                    ? "prawidłowy"
                    : "nieprawidłowa domena"
                  : "niepodany"
              }
              status={auctionUrl && isValidUrl ? "ok" : "warn"}
            />
          )}
          {email && (
            <SummaryRow
              icon={<Mail className="h-3 w-3" />}
              label="Konto"
              value={email}
              status="ok"
            />
          )}
          <SummaryRow
            icon={<ShieldCheck className="h-3 w-3" />}
            label="Zgoda"
            value={canSubmit ? "potwierdzona" : "wymagana"}
            status={canSubmit ? "ok" : "warn"}
          />
        </div>
        <p className="leading-relaxed">
          Uruchamiając analizę, jesteś świadomy/a, że LegitScore generuje{" "}
          <span className="font-medium text-slate-100">
            raport ryzyka autentyczności
          </span>{" "}
          na podstawie przesłanych zdjęć — to narzędzie pomocnicze, nie
          gwarancja.
        </p>
        {showDisclaimerCheckbox && (
          <SubmissionDisclaimer accepted={disclaimerAccepted} onChange={onDisclaimerChange} />
        )}
      </div>

      <div className="mt-4 space-y-2">
        <div className="flex justify-between gap-3">
          <Link
            href="/analyze"
            className="inline-flex items-center gap-1.5 rounded-full border border-border/80 bg-slate-950/40 px-4 py-2 text-xs font-medium text-muted-foreground hover:border-emerald-400/70 hover:text-emerald-200"
          >
            <ArrowLeft className="h-3 w-3" />
            Wróć do startu
          </Link>
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting}
            aria-disabled={!canSubmit}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-5 py-2.5 text-xs font-semibold shadow-lg transition",
              canSubmit && !submitting
                ? "bg-emerald-500 text-slate-950 shadow-emerald-500/50 hover:bg-emerald-400 hover:shadow-emerald-400/60"
                : "cursor-not-allowed bg-slate-800/60 text-slate-500 shadow-none"
            )}
          >
            {submitLabel}
            <ArrowRight className="h-3 w-3" />
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
          {!isLoggedIn ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/40 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-200">
              <Sparkles className="h-3 w-3" />
              Pierwsza analiza gratis po założeniu konta
            </span>
          ) : credits === null ? null : credits > 0 ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/40 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-200">
              <Sparkles className="h-3 w-3" />
              Dostępne analizy: {credits}
            </span>
          ) : (
            <Link
              href="/billing"
              className="inline-flex items-center gap-1 rounded-full border border-amber-400/40 bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold text-amber-200 transition hover:bg-amber-500/20"
            >
              Wykorzystałeś dostępne analizy — kup kolejną
              <ArrowRight className="h-3 w-3" />
            </Link>
          )}
          <span>Raport ryzyka, nie gwarancja.</span>
        </div>
      </div>
      </div>
    </aside>
  );
}

type SummaryRowProps = {
  icon: React.ReactNode;
  label: string;
  value: string;
  status?: "ok" | "warn";
  accent?: boolean;
};

function SummaryRow({
  icon,
  label,
  value,
  status,
  accent,
}: SummaryRowProps) {
  const statusIcon =
    status === "ok" ? (
      <CheckCircle2 className="h-3 w-3 text-emerald-300" />
    ) : status === "warn" ? (
      <Clock className="h-3 w-3 text-amber-300" />
    ) : null;

  return (
    <div className="flex items-start gap-2">
      <div className="flex shrink-0 items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-900/80 text-slate-200">
          {icon}
        </span>
        <span className="text-xs text-slate-300 whitespace-nowrap">{label}</span>
      </div>
      <div className="ml-auto flex min-w-0 items-center gap-1">
        {statusIcon && <span className="shrink-0">{statusIcon}</span>}
        <span
          className={cn(
            "block min-w-0 truncate text-right text-xs",
            accent ? "font-semibold text-slate-100" : "",
            status === "warn" && !accent ? "text-amber-300" : ""
          )}
          title={value}
        >
          {value}
        </span>
      </div>
    </div>
  );
}

