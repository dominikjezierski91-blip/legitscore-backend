import { CheckCircle2 } from "lucide-react";

const FREE_FEATURES = [
  "Pierwsza analiza gratis",
  "Nielimitowana Kolekcja koszulek",
  "Śledzenie wyceny rynkowej",
  "Pełna historia analiz",
  "Bonus +2 analizy",
];

/** Subtelny pasek nad kartą logowania/rejestracji — pokazuje wartość konta
 * zanim user w ogóle zacznie wypełniać formularz. */
export function FreeFeaturesStrip() {
  return (
    <div className="flex w-full max-w-sm flex-wrap items-center justify-center gap-1.5">
      {FREE_FEATURES.map((label) => (
        <span
          key={label}
          className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/20 bg-emerald-500/5 px-3 py-1 text-[11px] text-emerald-200/90"
        >
          <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-400" />
          {label}
        </span>
      ))}
    </div>
  );
}
