"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";
import { getCollection, deleteFromCollection, refreshMarketValue } from "@/lib/api";
import { Loader2, Trash2, ShieldCheck, Search, ChevronDown, ChevronUp, SlidersHorizontal, Pencil, Check, TrendingUp, TrendingDown, RefreshCw } from "lucide-react";
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
  const [collectionName, setCollectionName] = useState("Moja kolekcja");
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("Moja kolekcja");

  useEffect(() => {
    const saved = localStorage.getItem("collection_name");
    if (saved) { setCollectionName(saved); setNameInput(saved); }
  }, []);

  function saveCollectionName() {
    const trimmed = nameInput.trim() || "Moja kolekcja";
    setCollectionName(trimmed);
    setNameInput(trimmed);
    localStorage.setItem("collection_name", trimmed);
    setEditingName(false);
  }

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

  const handleMarketValueRefresh = (itemId: string, result: any) => {
    setItems((prev) => prev.map((i) => i.id === itemId ? { ...i, ...result } : i));
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
        <div className="flex items-center gap-2">
          {editingName ? (
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") saveCollectionName(); if (e.key === "Escape") setEditingName(false); }}
                className="rounded-lg border border-emerald-500/40 bg-slate-900/60 px-2 py-1 text-lg font-semibold text-slate-50 outline-none focus:border-emerald-400"
              />
              <button onClick={saveCollectionName} className="rounded-full p-1 text-emerald-400 hover:text-emerald-300">
                <Check className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <>
              <h1 className="text-xl font-semibold tracking-tight text-slate-50">{collectionName}</h1>
              <button onClick={() => setEditingName(true)} className="rounded-full p-1 text-slate-600 transition hover:text-slate-400">
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </>
          )}
        </div>
        <Link
          href="/analyze/form"
          className="inline-flex items-center justify-center gap-2 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400"
        >
          <Search className="h-3.5 w-3.5" />
          Rozpocznij kolejną analizę
        </Link>
      </div>

      {/* Portfel Koszulek — dashboard */}
      {items.length >= 1 && <PortfolioStats items={items} />}

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
            <CollectionCard key={item.id} item={item} onDelete={handleDelete} onMarketValueRefresh={handleMarketValueRefresh} />
          ))}
        </div>
      )}
    </div>
  );
}

function PortfolioStats({ items }: { items: any[] }) {
  const fx: Record<string, number> = { PLN: 1, EUR: 4.25, GBP: 5.0, USD: 3.9 };

  const totalInvested = items.reduce((sum, i) => {
    if (!i.purchase_price) return sum;
    const price = parseFloat(String(i.purchase_price).replace(",", "."));
    if (isNaN(price)) return sum;
    return sum + price * (fx[(i.purchase_currency || "PLN").toUpperCase()] ?? 1);
  }, 0);

  const totalMarket = items.reduce((sum, i) => {
    return sum + (i.market_value_pln ?? 0);
  }, 0);

  const itemsWithMarket = items.filter((i) => i.market_value_pln != null).length;
  const itemsWithPrice = items.filter((i) => i.purchase_price).length;
  const gain = totalMarket > 0 && totalInvested > 0 ? totalMarket - totalInvested : null;
  const roi = gain != null && totalInvested > 0 ? (gain / totalInvested) * 100 : null;

  const fmt = (n: number) => Math.round(n).toLocaleString("pl-PL");

  return (
    <div className="space-y-3">
      {/* Hero: wartość rynkowa */}
      {itemsWithMarket > 0 ? (
        <div className="glass-card space-y-3 p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Portfel Koszulek · wartość rynkowa</p>
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-3xl font-bold tracking-tight text-emerald-300">{fmt(totalMarket)} PLN</p>
              <p className="mt-0.5 text-[10px] text-slate-600">wycena {itemsWithMarket} z {items.length} koszulek</p>
            </div>
            {gain != null && (
              <div className={cn("text-right", gain >= 0 ? "text-emerald-400" : "text-red-400")}>
                <p className="flex items-center justify-end gap-1 text-lg font-semibold">
                  {gain >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                  {gain >= 0 ? "+" : ""}{fmt(gain)} PLN
                </p>
                {roi != null && (
                  <p className="text-[11px] opacity-80">{roi >= 0 ? "+" : ""}{roi.toFixed(1)}% ROI</p>
                )}
              </div>
            )}
          </div>
          {totalInvested > 0 && (
            <div className="flex items-center gap-2 border-t border-border/30 pt-2 text-[11px] text-slate-500">
              <span>Zainwestowano:</span>
              <span className="font-medium text-slate-300">{fmt(totalInvested)} PLN</span>
            </div>
          )}
        </div>
      ) : (
        totalInvested > 0 && (
          <div className="glass-card flex flex-col items-center gap-1 p-5 text-center">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Portfel Koszulek</p>
            <p className="text-3xl font-bold tracking-tight text-slate-100">{fmt(totalInvested)} PLN</p>
            <p className="text-[10px] text-slate-600">zainwestowano · {itemsWithPrice} z {items.length} koszulek z ceną</p>
            <p className="mt-1 text-[11px] text-slate-500">Rozwiń kartę i kliknij "Sprawdź wartość rynkową" aby zobaczyć zysk</p>
          </div>
        )
      )}
      {/* Statystyki pomocnicze */}
      {items.length >= 2 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="glass-card p-3 text-center">
            <p className="text-lg font-bold text-slate-100">{items.length}</p>
            <p className="text-[10px] text-muted-foreground">Koszulek</p>
          </div>
          <div className="glass-card p-3 text-center">
            <p className="text-lg font-bold text-red-300">{items.filter((i) => i.verdict_category === "podrobka").length}</p>
            <p className="text-[10px] text-muted-foreground">Podejrzanych</p>
          </div>
          <div className="glass-card p-3 text-center">
            <p className="text-lg font-bold text-slate-100">{itemsWithMarket}</p>
            <p className="text-[10px] text-muted-foreground">Wycenionych</p>
          </div>
        </div>
      )}
    </div>
  );
}

function JerseyThumbnail({ caseId, verdictCategory }: { caseId: string; verdictCategory?: string }) {
  const [imgError, setImgError] = useState(false);
  const isRisky = verdictCategory === "podrobka";
  const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");
  const src = `${apiBase}/api/cases/${caseId}/thumbnail`;

  const wrapperClass = cn(
    "relative flex h-16 w-11 flex-shrink-0 overflow-hidden rounded-lg border shadow-inner",
    isRisky ? "border-red-500/40" : "border-emerald-500/20"
  );

  if (!imgError) {
    return (
      <div className={wrapperClass}>
        <img
          src={src}
          alt=""
          onError={() => setImgError(true)}
          className="h-full w-full object-cover"
        />
      </div>
    );
  }

  // SVG jersey silhouette fallback
  return (
    <div className={cn(wrapperClass, isRisky ? "bg-red-950/40" : "bg-slate-800/60")}>
      <svg viewBox="0 0 44 64" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-full w-full p-1">
        {/* Shoulders */}
        <path d="M8 8 L4 18 L12 20 L12 56 L32 56 L32 20 L40 18 L36 8 L28 12 Q22 15 16 12 Z"
          fill={isRisky ? "rgba(239,68,68,0.15)" : "rgba(16,185,129,0.12)"}
          stroke={isRisky ? "rgba(239,68,68,0.4)" : "rgba(16,185,129,0.35)"}
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
        {/* Collar */}
        <path d="M16 12 Q22 17 28 12" stroke={isRisky ? "rgba(239,68,68,0.5)" : "rgba(16,185,129,0.5)"} strokeWidth="1.2" fill="none" strokeLinecap="round" />
      </svg>
    </div>
  );
}

function CollectionCard({ item, onDelete, onMarketValueRefresh }: { item: any; onDelete: (id: string) => void; onMarketValueRefresh: (id: string, result: any) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [valuating, setValuating] = useState(false);
  const vm = VERDICT_META[item.verdict_category] ?? {
    label: item.verdict_category ?? "—",
    bg: "bg-slate-500/20",
    text: "text-slate-300",
  };
  const confLabel = CONFIDENCE_LABELS[(item.confidence_level || "").toLowerCase()];

  const purchasePln = (() => {
    if (!item.purchase_price) return null;
    const price = parseFloat(String(item.purchase_price).replace(",", "."));
    if (isNaN(price)) return null;
    const fx: Record<string, number> = { PLN: 1, EUR: 4.25, GBP: 5.0, USD: 3.9 };
    return price * (fx[(item.purchase_currency || "PLN").toUpperCase()] ?? 1);
  })();
  const marketValue: number | null = item.market_value_pln ?? null;
  const gainPln = purchasePln != null && marketValue != null ? marketValue - purchasePln : null;

  async function handleValuate() {
    setValuating(true);
    try {
      const result = await refreshMarketValue(item.id);
      onMarketValueRefresh(item.id, result);
    } catch {
      // ignoruj błąd — user widzi brak wartości
    } finally {
      setValuating(false);
    }
  }

  return (
    <div className="glass-card overflow-hidden">
      {/* Collapsed view */}
      <div className="flex items-start gap-3 p-4">
        <JerseyThumbnail caseId={item.case_id} verdictCategory={item.verdict_category} />

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
            {marketValue != null && (
              <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
                ~{Math.round(marketValue).toLocaleString("pl-PL")} PLN
              </span>
            )}
            {gainPln != null && (
              <span className={cn(
                "flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[11px] font-semibold",
                gainPln >= 0
                  ? "bg-emerald-500/10 text-emerald-400"
                  : "bg-red-500/10 text-red-400"
              )}>
                {gainPln >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                {gainPln >= 0 ? "+" : ""}{Math.round(gainPln).toLocaleString("pl-PL")} PLN
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

          <div className="flex flex-wrap gap-2 pt-1">
            <Link
              href={`/case/${item.case_id}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/50 bg-emerald-500/10 px-4 py-2 text-[11px] font-medium text-emerald-200 transition hover:bg-emerald-500/20"
            >
              Zobacz pełny raport →
            </Link>
            <button
              onClick={handleValuate}
              disabled={valuating}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-600/60 bg-slate-800/40 px-4 py-2 text-[11px] font-medium text-slate-300 transition hover:border-emerald-400/40 hover:text-emerald-300 disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3 w-3", valuating && "animate-spin")} />
              {valuating ? "Szacuję..." : marketValue != null ? "Odśwież wycenę" : "Sprawdź wartość rynkową"}
            </button>
            {item.market_value_updated_at && (
              <span className="self-center text-[10px] text-slate-600">
                Wycena: {new Date(item.market_value_updated_at).toLocaleDateString("pl-PL")}
                {item.market_value_sample_size ? ` · ${item.market_value_sample_size} aukcji` : ""}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
