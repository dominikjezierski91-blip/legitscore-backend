"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";
import { getMyReports, type HistoriaItem } from "@/lib/api";
import { Loader2, Camera, Clock } from "lucide-react";

const VERDICT_META: Record<string, { label: string; bg: string; text: string }> = {
  oryginalna_sklepowa: { label: "Oryginalna (sklepowa)", bg: "bg-emerald-500/20", text: "text-emerald-300" },
  meczowa: { label: "Meczowa", bg: "bg-blue-500/20", text: "text-blue-300" },
  oficjalna_replika: { label: "Oficjalna replika", bg: "bg-amber-500/20", text: "text-amber-300" },
  podrobka: { label: "Podróbka", bg: "bg-red-500/20", text: "text-red-300" },
  edycja_limitowana: { label: "Edycja limitowana", bg: "bg-purple-500/20", text: "text-purple-300" },
  treningowa_custom: { label: "Treningowa / custom", bg: "bg-slate-500/20", text: "text-slate-300" },
};

// Ten sam zestaw co na /collection — model potrafi zwrócić placeholder zamiast
// realnej wartości, gdy nie ustalił klubu/zawodnika ze zdjęć.
const UNKNOWN_VALUES = new Set(["nieustalone", "unknown", "brak", "—", "n/a", "", "nie dotyczy", "niezweryfikowane"]);
function knownOrNull(value: string | null): string | null {
  if (!value) return null;
  return UNKNOWN_VALUES.has(value.trim().toLowerCase()) ? null : value;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("pl-PL", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

export default function HistoriaPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<HistoriaItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login?next=/historia");
      return;
    }
    getMyReports()
      .then(setItems)
      .catch((err: any) => setError(err.message || "Nie udało się pobrać historii."));
  }, [user, authLoading, router]);

  if (authLoading || (!user && !error)) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-5 py-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-50">Historia</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Wszystkie Twoje raporty — niezależnie od tego, czy dodałeś je do Kolekcji.
        </p>
      </div>

      {error && (
        <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>
      )}

      {items === null && !error && (
        <div className="flex flex-1 items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-emerald-400" />
        </div>
      )}

      {items !== null && items.length === 0 && (
        <div className="glass-card flex flex-col items-center gap-3 p-10 text-center">
          <Camera className="h-8 w-8 text-slate-500" />
          <p className="text-sm text-muted-foreground">Nie masz jeszcze żadnych raportów.</p>
          <Link
            href="/analyze/form"
            className="mt-1 inline-flex items-center justify-center gap-1.5 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-400"
          >
            Sprawdź koszulkę
          </Link>
        </div>
      )}

      {items !== null && items.length > 0 && (
        <div className="flex flex-col gap-2">
          {items.map((item) => {
            const meta = item.verdict_category ? VERDICT_META[item.verdict_category] : null;
            const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");
            const club = knownOrNull(item.club);
            const player = knownOrNull(item.player_name);
            const subjectLine = [club, player].filter(Boolean).join(" · ");
            return (
              <Link
                key={item.case_id}
                href={`/case/${item.case_id}`}
                className="glass-card flex items-center gap-3 p-3 transition hover:border-emerald-400/40"
              >
                <div className="flex h-14 w-10 flex-shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-slate-900/60">
                  <img
                    src={`${apiBase}/api/cases/${item.case_id}/thumbnail`}
                    alt=""
                    loading="lazy"
                    className="h-full w-full object-cover"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />
                </div>
                <div className="min-w-0 flex-1 space-y-0.5">
                  <div className="flex items-center gap-2">
                    {meta ? (
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${meta.bg} ${meta.text}`}>
                        {meta.label}
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 rounded-full bg-slate-700/40 px-2 py-0.5 text-[10px] font-medium text-slate-400">
                        <Clock className="h-2.5 w-2.5" />
                        W trakcie / niedostępna
                      </span>
                    )}
                    {item.confidence_percent !== null && (
                      <span className="text-[10px] text-muted-foreground">
                        {item.confidence_percent}% pewności
                      </span>
                    )}
                  </div>
                  {subjectLine && (
                    <p className="truncate text-xs font-medium text-slate-200">{subjectLine}</p>
                  )}
                  {item.summary && (
                    <p className="truncate text-xs text-slate-300">{item.summary}</p>
                  )}
                </div>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {fmtDate(item.created_at)}
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
