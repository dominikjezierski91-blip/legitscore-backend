import Link from "next/link";
import { ArrowRight } from "lucide-react";

export function AnalyzeCard() {
  return (
    <div className="glass-card relative overflow-hidden p-8">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-emerald-500/10 via-teal-400/5 to-transparent" />
      <div className="relative space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
          Analyze a football jersey with LegitScore
        </h1>
        <p className="max-w-xl text-sm text-muted-foreground">
          Upload photos of a shirt and receive a structured, risk-based
          authenticity analysis. Focused on evidence, not guarantees.
        </p>
        <div className="flex flex-wrap items-center gap-3 pt-2">
          <Link
            href="/analyze/form"
            className="inline-flex items-center gap-2 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 shadow-lg shadow-emerald-500/40 transition hover:bg-emerald-400"
          >
            Start new analysis
            <ArrowRight className="h-4 w-4" />
          </Link>
          <span className="text-xs text-muted-foreground">
            Currently in private beta. Expect occasional model quirks.
          </span>
        </div>
      </div>
    </div>
  );
}

