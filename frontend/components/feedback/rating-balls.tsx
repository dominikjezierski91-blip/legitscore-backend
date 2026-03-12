"use client";

import { useState, useEffect } from "react";
import { submitRating, getRating } from "@/lib/api";

type Props = {
  caseId: string;
};

export function RatingBalls({ caseId }: Props) {
  const [rating, setRating] = useState<number | null>(null);
  const [hoveredRating, setHoveredRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getRating(caseId)
      .then((data) => {
        if (data.rating) {
          setRating(data.rating);
          setSubmitted(true);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [caseId]);

  const handleSubmit = async () => {
    if (!rating) return;

    setSubmitting(true);
    try {
      await submitRating(caseId, rating, comment || undefined);
      setSubmitted(true);
    } catch (e) {
      console.error("Failed to submit rating:", e);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="text-xs text-muted-foreground">Ładowanie...</div>
    );
  }

  if (submitted) {
    return (
      <div className="space-y-2">
        <div className="text-xs font-semibold text-slate-100">
          Jak oceniasz ten raport?
        </div>
        <div className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map((n) => (
            <span
              key={n}
              className={`text-xl ${n <= (rating || 0) ? "opacity-100" : "opacity-30"}`}
            >
              ⚽
            </span>
          ))}
        </div>
        <p className="text-xs text-emerald-300">Dziękujemy za opinię!</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-xs font-semibold text-slate-100">
        Jak oceniasz ten raport?
      </div>

      <div className="flex items-center gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => setRating(n)}
            onMouseEnter={() => setHoveredRating(n)}
            onMouseLeave={() => setHoveredRating(null)}
            className={`text-2xl transition-all hover:scale-110 ${
              n <= (hoveredRating ?? rating ?? 0)
                ? "opacity-100"
                : "opacity-30 grayscale"
            }`}
          >
            ⚽
          </button>
        ))}
      </div>

      <p className="text-xs text-muted-foreground">
        Twoja opinia pomoże nam ulepszać analizy
      </p>

      {rating && (
        <>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Dodaj komentarz (opcjonalnie)"
            className="w-full rounded-xl border border-border/70 bg-slate-950/40 px-3 py-2 text-xs outline-none ring-emerald-500/40 placeholder:text-slate-500 focus:ring"
            rows={2}
          />
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="inline-flex items-center justify-center rounded-full bg-emerald-500 px-4 py-2 text-xs font-medium text-slate-950 shadow-md shadow-emerald-500/40 transition hover:bg-emerald-400 disabled:opacity-50"
          >
            {submitting ? "Wysyłanie..." : "Wyślij ocenę"}
          </button>
        </>
      )}
    </div>
  );
}
