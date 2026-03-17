"use client";

import { useState, useEffect } from "react";
import { submitFeedback, getFeedback, getCollection } from "@/lib/api";
import { CheckCircle, XCircle, HelpCircle, Lock } from "lucide-react";

type FeedbackValue = "correct" | "incorrect" | "unsure";

type Props = {
  caseId: string;
};

export function FeedbackButtons({ caseId }: Props) {
  const [selected, setSelected] = useState<FeedbackValue | null>(null);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [savedInCollection, setSavedInCollection] = useState(false);

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

  useEffect(() => {
    getCollection()
      .then((items: any[]) => {
        if (items.some((i) => i.case_id === caseId)) {
          setSavedInCollection(true);
        }
      })
      .catch(() => {});
  }, [caseId]);

  async function handleClick(value: FeedbackValue) {
    if (loading || (savedInCollection && saved)) return;
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

  const locked = savedInCollection && saved;

  const buttons: { value: FeedbackValue; label: string; icon: typeof CheckCircle; color: string }[] = [
    { value: "correct", label: "Poprawny", icon: CheckCircle, color: "emerald" },
    { value: "incorrect", label: "Niepoprawny", icon: XCircle, color: "red" },
    { value: "unsure", label: "Nie wiem", icon: HelpCircle, color: "amber" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-200">
        <span>Czy wynik analizy jest poprawny?</span>
        {locked && <Lock className="h-3 w-3 text-slate-500" />}
      </div>
      <div className="flex flex-wrap gap-2">
        {buttons.map(({ value, label, icon: Icon, color }) => {
          const isSelected = selected === value;
          const isDisabled = locked ? !isSelected : loading;

          const baseClasses = "flex items-center gap-2 rounded-full px-4 py-2 text-xs font-medium transition";

          let colorClasses: string;
          if (locked) {
            if (isSelected) {
              colorClasses =
                color === "emerald"
                  ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/40"
                  : color === "red"
                  ? "bg-red-500/15 text-red-400 border border-red-500/40"
                  : "bg-amber-500/15 text-amber-400 border border-amber-500/40";
            } else {
              colorClasses = "bg-slate-800/30 text-slate-600 border border-slate-700/40 cursor-default";
            }
          } else {
            colorClasses = isSelected
              ? color === "emerald"
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-400/60"
                : color === "red"
                ? "bg-red-500/20 text-red-300 border border-red-400/60"
                : "bg-amber-500/20 text-amber-300 border border-amber-400/60"
              : "bg-slate-800/60 text-slate-300 border border-slate-600/60 hover:bg-slate-700/60";
          }

          return (
            <button
              key={value}
              onClick={() => handleClick(value)}
              disabled={isDisabled}
              className={`${baseClasses} ${colorClasses} ${isDisabled && !isSelected ? "opacity-40" : ""}`}
            >
              <Icon className="h-4 w-4" />
              <span>{label}</span>
            </button>
          );
        })}
      </div>
      {saved && !locked && (
        <p className="text-[11px] text-slate-400">
          Dziękujemy za feedback! Pomoże nam to ulepszać model.
        </p>
      )}
      {locked && (
        <p className="text-[11px] text-slate-500">
          Ocena zapisana razem z koszulką w kolekcji.
        </p>
      )}
    </div>
  );
}
