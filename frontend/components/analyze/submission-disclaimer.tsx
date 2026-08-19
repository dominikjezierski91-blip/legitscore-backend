"use client";

import Link from "next/link";

type Props = {
  accepted: boolean;
  onChange: (accepted: boolean) => void;
};

// Tylko dla userów, którzy jeszcze nie zaakceptowali aktualnej wersji
// Regulaminu (goście, albo zalogowani po zmianie Regulaminu) — renderowany
// bezpośrednio przy przycisku "Uruchom analizę" w SubmitSummaryCard, nie jako
// osobny "krok" bez żadnej akcji. Dla już zaakceptowanych userów wystarcza
// istniejące zdanie "narzędzie pomocnicze, nie gwarancja" w tym samym miejscu.
export function SubmissionDisclaimer({ accepted, onChange }: Props) {
  return (
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
      <p>
        Dokładność raportu zależy od jakości i kompletności przesłanych zdjęć
        lub dostępności zdjęć w podanym ogłoszeniu.
      </p>
    </div>
  );
}

