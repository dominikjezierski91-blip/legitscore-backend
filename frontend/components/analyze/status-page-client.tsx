"use client";

import { useEffect, useState } from "react";
import { AnalyzeStatus } from "./analyze-status";
import { Loader2 } from "lucide-react";

function parseParams(): { caseId: string; mode: string } {
  if (typeof window === "undefined") return { caseId: "", mode: "" };
  const params = new URLSearchParams(window.location.search);
  return {
    caseId: params.get("case_id") ?? "",
    mode: params.get("mode") ?? "",
  };
}

export function StatusPageClient() {
  const [params, setParams] = useState<{ caseId: string; mode: string } | null>(
    null
  );

  useEffect(() => {
    setParams(parseParams());
  }, []);

  // Zawsze renderuj coś od pierwszej klatki – spinner dopóki nie znamy params
  if (params === null) {
    return (
      <div className="flex flex-1 items-center justify-center py-8">
        <div className="glass-card flex w-full max-w-md flex-col items-center justify-center gap-4 p-8 text-center">
          <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
          <h1 className="text-lg font-semibold tracking-tight text-slate-50">
            Analizujemy koszulkę
          </h1>
          <p className="text-xs text-muted-foreground">
            Trwa analiza. Sprawdzamy detale, metki i spójność wykonania...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 items-center justify-center py-8">
      <AnalyzeStatus caseId={params.caseId} mode={params.mode} />
    </div>
  );
}
