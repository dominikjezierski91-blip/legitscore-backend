"use client";

import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock,
  ImageIcon,
  Mail,
  ShieldCheck,
} from "lucide-react";
import { ReportType } from "./report-type-selector";
import { cn } from "@/lib/utils";

type Props = {
  reportType: ReportType;
  imageCount: number;
  minImages: number;
  email: string;
  canSubmit: boolean;
  onSubmit: () => void;
  submitting: boolean;
};

export function SubmitSummaryCard({
  reportType,
  imageCount,
  minImages,
  email,
  canSubmit,
  onSubmit,
  submitting,
}: Props) {
  return (
    <aside className="flex flex-col justify-between rounded-2xl border border-emerald-500/20 bg-slate-900/70 p-5 shadow-[0_18px_45px_rgba(16,185,129,0.25)] backdrop-blur md:sticky md:top-6 md:self-start">
      <div className="space-y-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-2 text-[11px] font-semibold text-slate-100">
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
          <SummaryRow
            icon={<Mail className="h-3 w-3" />}
            label="Email kontaktowy"
            value={email || "niepodany"}
            status={email ? "ok" : "warn"}
          />
          <SummaryRow
            icon={<ShieldCheck className="h-3 w-3" />}
            label="Zgoda"
            value={canSubmit ? "potwierdzona" : "wymagana"}
            status={canSubmit ? "ok" : "warn"}
          />
        </div>
        <p className="leading-relaxed">
          LegitScore generuje{" "}
          <span className="font-medium text-slate-100">
            raport ryzyka autentyczności
          </span>{" "}
          na podstawie przesłanych zdjęć. To narzędzie pomocnicze, nie
          gwarancja.
        </p>
      </div>

      <div className="mt-4 space-y-2">
        <div className="flex justify-between gap-3">
          <Link
            href="/analyze"
            className="inline-flex items-center gap-1.5 rounded-full border border-border/80 bg-slate-950/40 px-4 py-2 text-[11px] font-medium text-muted-foreground hover:border-emerald-400/70 hover:text-emerald-200"
          >
            <ArrowLeft className="h-3 w-3" />
            Wróć do startu
          </Link>
          <button
            type="button"
            onClick={onSubmit}
            disabled={!canSubmit || submitting}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-5 py-2.5 text-[11px] font-semibold shadow-lg transition",
              canSubmit && !submitting
                ? "bg-emerald-500 text-slate-950 shadow-emerald-500/50 hover:bg-emerald-400 hover:shadow-emerald-400/60"
                : "cursor-not-allowed bg-slate-800/60 text-slate-500 shadow-none"
            )}
          >
            {submitting ? "Wysyłanie..." : "Uruchom analizę"}
            <ArrowRight className="h-3 w-3" />
          </button>
        </div>
        <div className="text-[11px] text-muted-foreground">
          <div>Darmowe w becie.</div>
          <div>Raport ryzyka, nie gwarancja.</div>
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
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-900/80 text-slate-200">
          {icon}
        </span>
        <span className="text-[11px] text-slate-300">{label}</span>
      </div>
      <div className="flex items-center gap-1">
        {statusIcon}
        <span
          className={cn(
            "break-all text-right text-[11px]",
            accent ? "font-semibold text-slate-100" : "",
            status === "warn" && !accent ? "text-amber-300" : ""
          )}
        >
          {value}
        </span>
      </div>
    </div>
  );
}

