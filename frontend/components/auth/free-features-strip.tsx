import { CheckCircle2 } from "lucide-react";

const FREE_FEATURES = [
  "Pierwszą analizę koszulki całkowicie za darmo.",
  "Nielimitowaną Kolekcję — trzymaj wszystkie swoje koszulki w jednym miejscu.",
  "Bieżącą wycenę rynkową każdej koszulki w Twojej kolekcji.",
  "Pełną historię wszystkich wykonanych analiz.",
  "Bonus +2 dodatkowe analizy po pierwszym sprawdzeniu koszulki.",
];

/** Lista korzyści nad kartą logowania/rejestracji — pokazuje wartość konta
 * pełnymi zdaniami, zanim user w ogóle zacznie wypełniać formularz. */
export function FreeFeaturesStrip() {
  return (
    <div className="w-full max-w-sm space-y-2.5 rounded-2xl border border-emerald-400/15 bg-emerald-500/[0.04] p-4">
      <p className="text-xs font-semibold text-emerald-200">
        Po założeniu darmowego konta otrzymujesz:
      </p>
      <ul className="space-y-1.5">
        {FREE_FEATURES.map((label) => (
          <li key={label} className="flex items-start gap-2 text-xs text-slate-300">
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
            <span>{label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
