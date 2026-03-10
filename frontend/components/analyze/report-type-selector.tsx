"use client";

import { cn } from "@/lib/utils";

export type ReportType = "basic" | "expert";

type Props = {
  value: ReportType;
  onChange: (value: ReportType) => void;
};

export function ReportTypeSelector({ value, onChange }: Props) {
  return (
    <section className="glass-card space-y-4 p-5 md:p-6">
      <div>
        <h2 className="text-sm font-semibold text-slate-100">
          Wybierz typ raportu
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Obie wersje są darmowe w becie. BASIC jest szybszy, EXPERT
          dokładniejszy.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <button
          type="button"
          onClick={() => onChange("basic")}
          className={cn(
            "flex h-full flex-col items-start rounded-2xl border px-4 py-3 text-left text-xs transition",
            "bg-slate-950/40 hover:border-emerald-400/60 hover:bg-slate-900/60",
            value === "basic"
              ? "border-emerald-400 bg-emerald-500/10 shadow-md shadow-emerald-500/30"
              : "border-border/80"
          )}
        >
          <div className="mb-1 text-[11px] font-semibold text-slate-100">
            BASIC
          </div>
          <ul className="space-y-0.5 text-[11px] text-muted-foreground">
            <li>• Szybsza ocena ryzyka</li>
            <li>• Dla większości standardowych przypadków</li>
          </ul>
        </button>

        <button
          type="button"
          onClick={() => onChange("expert")}
          className={cn(
            "flex h-full flex-col items-start rounded-2xl border px-4 py-3 text-left text-xs transition",
            "bg-slate-950/40 hover:border-emerald-400/60 hover:bg-slate-900/60",
            value === "expert"
              ? "border-emerald-400 bg-emerald-500/10 shadow-md shadow-emerald-500/30"
              : "border-border/80"
          )}
        >
          <div className="mb-1 text-[11px] font-semibold text-slate-100">
            EXPERT
          </div>
          <ul className="space-y-0.5 text-[11px] text-muted-foreground">
            <li>• Dokładniejsza analiza</li>
            <li>• Dla trudniejszych lub bardziej wartościowych koszulek</li>
          </ul>
        </button>
      </div>
    </section>
  );
}

