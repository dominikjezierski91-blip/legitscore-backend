"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";
import { getCollection, deleteFromCollection } from "@/lib/api";
import { Loader2, Trash2, ShieldCheck, Search, ChevronDown, ChevronUp, SlidersHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

const VERDICT_META: Record<string, { label: string; bg: string; text: string }> = {
  oryginalna_sklepowa: { label: "Oryginalna (sklepowa)", bg: "bg-emerald-500/20", text: "text-emerald-300" },
  meczowa: { label: "Meczowa", bg: "bg-blue-500/20", text: "text-blue-300" },
  oficjalna_replika: { label: "Oficjalna replika", bg: "bg-amber-500/20", text: "text-amber-300" },
  podrobka: { label: "Podróbka", bg: "bg-red-500/20", text: "text-red-300" },
  edycja_limitowana: { label: "Edycja limitowana", bg: "bg-purple-500/20", text: "text-purple-300" },
  treningowa_custom: { label: "Treningowa / custom", bg: "bg-slate-500/20", text: "text-slate-300" },
};

const CONFIDENCE_LABELS: Record<string, string> = {
  bardzo_wysoki: "Bardzo wysoka",
  wysoki: "Wysoka",
  sredni: "Średnia",
  ograniczony: "Ograniczona",
};

type SortKey = "newest" | "oldest" | "club";

function pluralItems(n: number) {
  if (n === 1) return "1 koszulka";
  if (n >= 2 && n <= 4) return `${n} koszulki`;
  return `${n} koszulek`;
}

export default function CollectionPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>("newest");

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace("/login?next=/collection"); return; }
    getCollection()
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [user, authLoading, router]);

  const sorted = [...items].sort((a, b) => {
    if (sort === "club") return (a.club || "").localeCompare(b.club || "");
    if (sort === "oldest") return new Date(a.added_at || 0).getTime() - new Date(b.added_at || 0).getTime();
    return new Date(b.added_at || 0).getTime() - new Date(a.added_at || 0).getTime();
  });

  const handleDelete = async (itemId: string) => {
    if (!confirm("Usunąć tę koszulkę z kolekcji?")) return;
    try {
      await deleteFromCollection(itemId);
      setItems((prev) => prev.filter((i) => i.id !== itemId));
    } catch (e: any) {
      alert(e.message || "Nie udało się usunąć.");
    }
  };

  if (authLoading || loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex flex-1 flex-col gap-6 py-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-50">Moja kolekcja</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {loading ? "…" : items.length === 0 ? "Brak koszulek" : pluralItems(items.length)}
          </p>
        </div>
        <Link
          href="/analyze/form"
          className="inline-flex items-center justify-center gap-2 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400"
        >
          <Search className="h-3.5 w-3.5" />
          Rozpocznij kolejną analizę
        </Link>
      </div>

      {/* Mini dashboard */}
      {items.length >= 2 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="glass-card p-3 text-center">
            <p className="text-lg font-bold text-emerald-300">{items.length}</p>
            <p className="text-[10px] text-muted-foreground">Koszulek</p>
          </div>
          <div className="glass-card p-3 text-center">
            <p className="text-lg font-bold text-red-300">
              {items.filter((i) => i.verdict_category === "podrobka").length}
            </p>
            <p className="text-[10px] text-muted-foreground">Podejrzanych</p>
          </div>
          <div className="glass-card p-3 text-center">
            <p className="text-lg font-bold text-slate-100">
              {items.filter((i) => i.purchase_price).length}
            </p>
            <p className="text-[10px] text-muted-foreground">Z ceną</p>
          </div>
        </div>
      )}

      {/* Sort */}
      {items.length > 1 && (
        <div className="flex items-center gap-2 text-xs">
          <SlidersHorizontal className="h-3.5 w-3.5 text-slate-500" />
          <span className="text-slate-500">Sortuj:</span>
          {(["newest", "oldest", "club"] as SortKey[]).map((key) => (
            <button
              key={key}
              onClick={() => setSort(key)}
              className={cn(
                "rounded-full px-3 py-1 transition",
                sort === key ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:text-slate-200"
              )}
            >
              {key === "newest" ? "Najnowsze" : key === "oldest" ? "Najstarsze" : "Klub"}
            </button>
          ))}
        </div>
      )}

      {error && <div className="glass-card p-4 text-sm text-red-300">{error}</div>}

      {items.length === 0 && !error && (
        <div className="glass-card flex flex-col items-center gap-4 p-10 text-center">
          <ShieldCheck className="h-10 w-10 text-slate-600" />
          <div>
            <p className="font-medium text-slate-300">Kolekcja jest pusta</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Sprawdź koszulkę i dodaj ją do kolekcji z result page.
            </p>
          </div>
          <Link
            href="/analyze"
            className="rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400"
          >
            Sprawdź koszulkę
          </Link>
        </div>
      )}

      {sorted.length > 0 && (
        <div className="flex flex-col gap-3">
          {sorted.map((item) => (
            <CollectionCard key={item.id} item={item} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  );
}

function JerseyThumbnail({ club, verdictCategory }: { club?: string; verdictCategory?: string }) {
  const isRisky = verdictCategory === "podrobka";
  const initials = club
    ? club.split(/\s+/).map((w: string) => w[0]).join("").slice(0, 2).toUpperCase()
    : "?";

  return (
    <div
      className={cn(
        "relative flex h-16 w-11 flex-shrink-0 flex-col items-center justify-center overflow-hidden rounded-lg border shadow-inner",
        isRisky
          ? "border-red-500/40 bg-gradient-to-b from-red-950/80 to-slate-900"
          : "border-emerald-500/20 bg-gradient-to-b from-slate-700/80 to-slate-900"
      )}
    >
      {/* Collar hint */}
      <div className="absolute -top-1.5 left-1/2 h-3 w-9 -translate-x-1/2 rounded-b-full border border-border/30 bg-slate-800/60" />
      <span
        className={cn(
          "z-10 mt-2 text-[11px] font-bold tracking-wide",
          isRisky ? "text-red-400" : "text-slate-300"
        )}
      >
        {initials}
      </span>
    </div>
  );
}

function CollectionCard({ item, onDelete }: { item: any; onDelete: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const vm = VERDICT_META[item.verdict_category] ?? {
    label: item.verdict_category ?? "—",
    bg: "bg-slate-500/20",
    text: "text-slate-300",
  };
  const confLabel = CONFIDENCE_LABELS[(item.confidence_level || "").toLowerCase()];

  return (
    <div className="glass-card overflow-hidden">
      {/* Collapsed view */}
      <div className="flex items-start gap-3 p-4">
        <JerseyThumbnail club={item.club} verdictCategory={item.verdict_category} />

        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-semibold text-slate-100">
                {item.club || "Nieznany klub"}
              </p>
              <p className="text-xs text-muted-foreground">
                {item.season || "—"}
                {item.brand ? ` · ${item.brand}` : ""}
              </p>
            </div>
            <button
              onClick={() => onDelete(item.id)}
              className="shrink-0 rounded-full p-1.5 text-slate-600 transition hover:text-red-400"
              aria-label="Usuń z kolekcji"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>

          {(item.player_name || item.player_number) && (
            <p className="text-xs text-slate-400">
              {item.player_name}
              {item.player_number ? ` #${item.player_number}` : ""}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", vm.bg, vm.text)}>
              {vm.label}
            </span>
            {item.purchase_price && (
              <span className="rounded-full border border-slate-600/60 bg-slate-800/60 px-2 py-0.5 text-[11px] font-medium text-slate-200">
                {item.purchase_price} {item.purchase_currency || "PLN"}
              </span>
            )}
          </div>

          <div className="flex items-center justify-between pt-0.5">
            <span className="text-[10px] text-slate-600">
              {item.added_at ? new Date(item.added_at).toLocaleDateString("pl-PL") : "—"}
            </span>
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-[11px] text-emerald-600 transition hover:text-emerald-400"
            >
              {expanded ? "Zwiń" : "Pokaż szczegóły"}
              {expanded ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Expanded view */}
      {expanded && (
        <div className="border-t border-border/40 px-4 pb-4 pt-3 space-y-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
            {item.sku && (
              <>
                <dt className="text-slate-500">SKU</dt>
                <dd className="font-mono text-slate-300">{item.sku}</dd>
              </>
            )}
            {item.model_type && (
              <>
                <dt className="text-slate-500">Model</dt>
                <dd className="text-slate-300">{item.model_type}</dd>
              </>
            )}
            {item.report_mode && (
              <>
                <dt className="text-slate-500">Tryb raportu</dt>
                <dd className="text-slate-300">{item.report_mode === "expert" ? "Expert" : "Basic"}</dd>
              </>
            )}
            {confLabel && (
              <>
                <dt className="text-slate-500">Pewność analizy</dt>
                <dd className="text-slate-300">{confLabel}</dd>
              </>
            )}
            {item.purchase_source && (
              <>
                <dt className="text-slate-500">Źródło zakupu</dt>
                <dd className="text-slate-300">{item.purchase_source}</dd>
              </>
            )}
            {item.purchase_date && (
              <>
                <dt className="text-slate-500">Data zakupu</dt>
                <dd className="text-slate-300">
                  {new Date(item.purchase_date).toLocaleDateString("pl-PL")}
                </dd>
              </>
            )}
          </dl>

          {item.notes && (
            <div className="text-[11px]">
              <p className="text-slate-500">Notatki</p>
              <p className="mt-0.5 text-slate-300">{item.notes}</p>
            </div>
          )}

          <div className="pt-1">
            <Link
              href={`/case/${item.case_id}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/50 bg-emerald-500/10 px-4 py-2 text-[11px] font-medium text-emerald-200 transition hover:bg-emerald-500/20"
            >
              Zobacz pełny raport →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
