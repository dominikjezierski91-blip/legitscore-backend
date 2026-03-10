import Link from "next/link";
import { CheckCircle2, ArrowRight, ArrowLeft } from "lucide-react";

type Props = {
  caseId?: string;
  mode?: string;
};

export function AnalyzeSuccess({ caseId, mode }: Props) {
  const prettyMode =
    mode === "expert" ? "EXPERT" : mode === "basic" ? "BASIC" : undefined;

  return (
    <div className="glass-card flex flex-col items-center justify-center gap-4 p-8 text-center">
      <CheckCircle2 className="h-10 w-10 text-emerald-400" />
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-50">
          Zgłoszenie przyjęte
        </h1>
        <p className="max-w-md text-sm text-muted-foreground">
          Analiza została uruchomiona dla tej koszulki. Raport ryzyka
          autentyczności powstaje na podstawie przesłanych zdjęć.
        </p>
      </div>
      <div className="space-y-1 text-xs text-muted-foreground">
        {caseId && (
          <p>
            <span className="font-semibold text-slate-100">ID sprawy:</span>{" "}
            <span className="font-mono text-emerald-300">{caseId}</span>
          </p>
        )}
        {prettyMode && (
          <p>
            <span className="font-semibold text-slate-100">Tryb raportu:</span>{" "}
            {prettyMode}
          </p>
        )}
        <p>
          LegitScore dostarcza{" "}
          <span className="font-semibold text-emerald-300">
            raport ryzyka autentyczności
          </span>
          , nie certyfikat.
        </p>
        <p className="text-[11px]">
          Zachowaj ten numer sprawy. Może być potrzebny przy dalszym kontakcie.
        </p>
      </div>
      <div className="mt-4 flex gap-3">
        <Link
          href="/analyze/form"
          className="inline-flex items-center gap-1.5 rounded-full border border-border/80 bg-slate-950/40 px-4 py-2 text-xs font-medium text-muted-foreground hover:border-emerald-400/70 hover:text-emerald-200"
        >
          <ArrowLeft className="h-3 w-3" />
          Nowa analiza
        </Link>
        <Link
          href="/analyze/form"
          className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500 px-4 py-2 text-xs font-medium text-slate-950 shadow-md shadow-emerald-500/40 hover:bg-emerald-400"
        >
          Wróć do formularza
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
    </div>
  );
}

