"use client";

import { useState, useEffect } from "react";
import { submitFeedback, getFeedback } from "@/lib/api";
import { CheckCircle, XCircle, HelpCircle } from "lucide-react";

type FeedbackValue = "correct" | "incorrect" | "unsure";

type Props = {
  caseId: string;
};

export function FeedbackButtons({ caseId }: Props) {
  const [selected, setSelected] = useState<FeedbackValue | null>(null);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getFeedback(caseId)
      .then((data) => {
        if (data.feedback) {
          setSelected(data.feedback as FeedbackValue);
          setSaved(true);
        }
      })
      .catch(() => {});
  }, [caseId]);

  async function handleClick(value: FeedbackValue) {
    if (loading) return;
    setLoading(true);
    try {
      await submitFeedback(caseId, value);
      setSelected(value);
      setSaved(true);
    } catch (e) {
      console.error("Failed to save feedback", e);
    } finally {
      setLoading(false);
    }
  }

  const buttons: { value: FeedbackValue; label: string; icon: typeof CheckCircle; color: string }[] = [
    { value: "correct", label: "Poprawny", icon: CheckCircle, color: "emerald" },
    { value: "incorrect", label: "Niepoprawny", icon: XCircle, color: "red" },
    { value: "unsure", label: "Nie wiem", icon: HelpCircle, color: "amber" },
  ];

  return (
    <div className="space-y-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-200">
        Czy wynik analizy jest poprawny?
      </div>
      <div className="flex flex-wrap gap-2">
        {buttons.map(({ value, label, icon: Icon, color }) => {
          const isSelected = selected === value;
          const baseClasses = "flex items-center gap-2 rounded-full px-4 py-2 text-xs font-medium transition";
          const colorClasses = isSelected
            ? color === "emerald"
              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-400/60"
              : color === "red"
              ? "bg-red-500/20 text-red-300 border border-red-400/60"
              : "bg-amber-500/20 text-amber-300 border border-amber-400/60"
            : "bg-slate-800/60 text-slate-300 border border-slate-600/60 hover:bg-slate-700/60";

          return (
            <button
              key={value}
              onClick={() => handleClick(value)}
              disabled={loading}
              className={`${baseClasses} ${colorClasses}`}
            >
              <Icon className="h-4 w-4" />
              <span>{label}</span>
            </button>
          );
        })}
      </div>
      {saved && (
        <p className="text-[11px] text-slate-400">
          Dziękujemy za feedback! Pomoże nam to ulepszać model.
        </p>
      )}
    </div>
  );
}
