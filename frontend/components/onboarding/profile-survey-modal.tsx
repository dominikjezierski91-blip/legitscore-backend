"use client";

import { useState } from "react";
import { submitProfileSurvey, skipProfileSurvey } from "@/lib/api";

const USER_TYPE_OPTIONS = [
  { value: "kolekcjoner", label: "Kolekcjoner" },
  { value: "okazjonalny_kupujacy", label: "Okazjonalny kupujący" },
  { value: "sprzedajacy", label: "Sprzedający" },
];

const COLLECTION_SIZE_OPTIONS = [
  { value: "0-5", label: "0–5" },
  { value: "6-20", label: "6–20" },
  { value: "21-50", label: "21–50" },
  { value: "50+", label: "50+" },
];

type Props = {
  onDone: () => void;
};

export function ProfileSurveyModal({ onDone }: Props) {
  const [userType, setUserType] = useState("");
  const [collectionSize, setCollectionSize] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit() {
    if (!userType || !collectionSize) return;
    setSaving(true);
    try {
      await submitProfileSurvey(userType, collectionSize);
    } catch {
      // nie blokuj — dane opcjonalne
    } finally {
      setSaving(false);
      onDone();
    }
  }

  async function handleSkip() {
    try {
      await skipProfileSurvey();
    } catch {
      // ignoruj
    }
    onDone();
  }

  const canSubmit = !!userType && !!collectionSize;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm px-4">
      <div className="glass-card w-full max-w-sm space-y-6 p-7">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-emerald-500 mb-1">
            Krok 2 z 2
          </p>
          <h2 className="text-lg font-semibold text-slate-50">
            Poznajmy Twoje potrzeby
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Pomóż nam lepiej dopasować LegitScore do tego, jak korzystasz z koszulek piłkarskich.
          </p>
        </div>

        {/* Q1 */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-slate-300">
            Które określenie najlepiej do Ciebie pasuje?
          </p>
          <div className="flex flex-col gap-2">
            {USER_TYPE_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => setUserType(o.value)}
                className={`rounded-xl border px-4 py-2.5 text-sm text-left transition ${
                  userType === o.value
                    ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-300"
                    : "border-border/60 bg-slate-900/40 text-slate-300 hover:border-slate-500"
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        {/* Q2 */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-slate-300">
            Ile koszulek masz obecnie?
          </p>
          <div className="grid grid-cols-4 gap-2">
            {COLLECTION_SIZE_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => setCollectionSize(o.value)}
                className={`rounded-xl border px-2 py-2.5 text-sm text-center transition ${
                  collectionSize === o.value
                    ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-300"
                    : "border-border/60 bg-slate-900/40 text-slate-300 hover:border-slate-500"
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-2">
          <button
            onClick={handleSubmit}
            disabled={!canSubmit || saving}
            className="w-full rounded-full bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-400 disabled:opacity-40"
          >
            {saving ? "Zapisywanie..." : "Zapisz i przejdź dalej"}
          </button>
          <button
            onClick={handleSkip}
            disabled={saving}
            className="w-full rounded-full border border-border/50 px-4 py-2 text-sm text-slate-500 transition hover:text-slate-300"
          >
            Pomiń na teraz
          </button>
        </div>
      </div>
    </div>
  );
}
