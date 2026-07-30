"use client";

import Link from "next/link";

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
            Zapoznałem/am się i akceptuję{" "}
            <Link
              href="/regulamin"
              target="_blank"
              rel="noopener noreferrer"
              className="text-emerald-300 underline"
              onClick={(e) => e.stopPropagation()}
            >
              Regulamin
            </Link>{" "}
            oraz przyjmuję do wiadomości, że analiza LegitScore to ocena ryzyka,
            a nie certyfikat autentyczności.
          </span>
        </label>
        <p className="text-xs">
          Dokładność raportu zależy od jakości i kompletności przesłanych zdjęć
          lub dostępności zdjęć w podanym ogłoszeniu.
        </p>
      </div>
    </section>
  );
}

