"use client";

type Props = {
  accepted: boolean;
  onChange: (accepted: boolean) => void;
};

export function SubmissionDisclaimer({ accepted, onChange }: Props) {
  return (
    <section className="glass-card space-y-3 p-5 md:p-6">
      <div className="space-y-2 text-xs text-muted-foreground">
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={accepted}
            onChange={(e) => onChange(e.target.checked)}
            className="mt-0.5 h-3.5 w-3.5 cursor-pointer rounded border-border bg-slate-950/70 text-emerald-500 outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
          />
          <span>
            Rozumiem, że LegitScore generuje raport oceny ryzyka. To nie jest
            certyfikat autentyczności ani gwarancja.
          </span>
        </label>
        <p className="text-xs">
          Dokładność raportu zależy od jakości i kompletności przesłanych
          zdjęć.
        </p>
      </div>
    </section>
  );
}

