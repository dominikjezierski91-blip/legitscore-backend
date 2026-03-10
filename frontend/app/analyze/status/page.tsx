import { Suspense } from "react";
import { Loader2 } from "lucide-react";
import { StatusPageClient } from "@/components/analyze/status-page-client";

function StatusFallback() {
  return (
    <div className="flex flex-1 items-center justify-center py-8">
      <div className="glass-card flex w-full max-w-md flex-col items-center justify-center gap-4 p-8 text-center">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
        <h1 className="text-lg font-semibold tracking-tight text-slate-50">
          Analizujemy koszulkę
        </h1>
        <p className="text-xs text-muted-foreground">
          Sprawdzamy detale, metki i spójność wykonania...
        </p>
      </div>
    </div>
  );
}

export default function AnalyzeStatusPage() {
  return (
    <Suspense fallback={<StatusFallback />}>
      <StatusPageClient />
    </Suspense>
  );
}

