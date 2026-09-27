import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

// SPEC "Darmowe analizy w becie + ukrycie płatności za feature flagą"
// (2026-09-27), §4: jedno źródło copy dla wszystkich miejsc, gdzie wcześniej
// była cena/CTA płatności — nie duplikować tekstu w komponentach.
export const BETA_FREE_BADGE_TEXT = "Darmowe w wersji beta";
export const BETA_FREE_SENTENCE = "W wersji beta wszystkie analizy są bezpłatne.";
export const BETA_FREE_LOGGED_IN_SENTENCE =
  "Korzystasz z bezpłatnego dostępu w wersji beta.";
// SPEC §8c: darmowość w becie w zamian za zgodę na wykorzystanie danych do
// rozwoju modeli — link do Regulaminu/Polityki obok badge tam, gdzie jest
// miejsce na dłuższy tekst (nie w samym badge/pigułce).
export const BETA_FREE_DATA_NOTICE =
  "Bezpłatnie w becie — w zamian wykorzystujemy przesłane dane do ulepszania modeli.";

export function BetaFreeBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-300",
        className
      )}
    >
      <Sparkles className="h-3.5 w-3.5" />
      {BETA_FREE_BADGE_TEXT}
    </span>
  );
}
