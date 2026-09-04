"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";
import {
  getCollection, deleteFromCollection, refreshMarketValue,
  getCollectionThumbnailUrl,
} from "@/lib/api";
import {
  Loader2, Trash2, ShieldCheck, Search, ChevronDown, ChevronUp,
  SlidersHorizontal, Pencil, Check, TrendingUp, TrendingDown, RefreshCw,
  X, Plus, Bookmark, BookmarkCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { JerseyFormModal } from "@/components/collection/jersey-form-modal";

const VERDICT_META: Record<string, { label: string; short: string; bg: string; text: string }> = {
  oryginalna_sklepowa: { label: "Oryginalna (sklepowa)", short: "Sklepowa", bg: "bg-emerald-500/20", text: "text-emerald-300" },
  meczowa: { label: "Meczowa", short: "Meczowa", bg: "bg-blue-500/20", text: "text-blue-300" },
  oficjalna_replika: { label: "Oficjalna replika", short: "Replika", bg: "bg-amber-500/20", text: "text-amber-300" },
  podrobka: { label: "Podróbka", short: "Podróbka", bg: "bg-red-500/20", text: "text-red-300" },
  edycja_limitowana: { label: "Edycja limitowana", short: "Limitowana", bg: "bg-purple-500/20", text: "text-purple-300" },
  treningowa_custom: { label: "Treningowa / custom", short: "Treningowa", bg: "bg-slate-500/20", text: "text-slate-300" },
};

const FX_TO_PLN: Record<string, number> = { PLN: 1, EUR: 4.25, GBP: 5.0, USD: 3.9 };

// Podróbki nie mają sprawdzanej wartości rynkowej (nie ma sensu jej szukać na
// aukcjach) — wszędzie, gdzie liczymy/sortujemy "wartość", dla podróbki liczy
// się cena zakupu (jeśli user ją podał), tak jak dla zwykłych koszulek liczy
// się market_value_pln. Bez podanej ceny liczy się jako 0 (nie null) — podróbka
// ma zawsze wliczoną wartość do Portfela, user może dodać cenę zakupu później.
function effectiveItemValue(item: any): number | null {
  if (item.verdict_category === "podrobka") {
    if (!item.purchase_price) return 0;
    const price = parseFloat(String(item.purchase_price).replace(",", "."));
    if (isNaN(price)) return 0;
    return price * (FX_TO_PLN[(item.purchase_currency || "PLN").toUpperCase()] ?? 1);
  }
  return item.market_value_pln ?? null;
}

// "high" nie dostaje ostrzeżenia (wystarczy sama liczba ofert obok daty) —
// tylko "medium"/"low" jawnie mówią userowi że wycena jest orientacyjna,
// żeby nie sugerować fałszywej precyzji przy słabej próbce.
function marketValueConfidenceLabel(confidence: string | null | undefined): string | null {
  if (confidence === "medium") return "Wycena orientacyjna";
  if (confidence === "low") return "Wycena orientacyjna — mało ofert porównawczych";
  return null;
}

// Podróbki nigdy nie dostaną market_value_pln (backend celowo go nie liczy —
// patrz effectiveItemValue) — bez tego wykluczenia polling niżej odpytywałby
// API co 5s przez 30s za każdym razem, gdy w kolekcji jest choć jedna podróbka,
// mimo że nigdy nie doczeka się wyceny.
function isPendingValuation(item: any): boolean {
  return item.verdict_category !== "podrobka" && item.market_value_pln == null;
}

function fmtSeason(s: string | null | undefined): string {
  if (!s) return "";
  const m = s.match(/^(\d{4})[\/\-](\d{4})$/);
  if (m) return `${m[1].slice(2)}/${m[2].slice(2)}`;
  const m2 = s.match(/^(\d{4})[\/\-](\d{2})$/);
  if (m2) return `${m2[1].slice(2)}/${m2[2]}`;
  return s;
}

// Feature 3: extend SortKey
type SortKey = "newest" | "oldest" | "club" | "expensive" | "cheap";

// Feature 1: filter type
type FilterKey = "all" | "suspicious" | "valuated" | "no_analysis" | null;

function pluralItems(n: number) {
  if (n === 1) return "1 koszulka";
  if (n >= 2 && n <= 4) return `${n} koszulki`;
  return `${n} koszulek`;
}

const SORT_LABELS: Record<SortKey, string> = {
  newest: "Najnowsze", oldest: "Najstarsze", expensive: "Najdroższe", cheap: "Najtańsze", club: "Klub",
};

const FILTER_LABELS: Record<string, string> = {
  all: "Wszystkie", valuated: "Wycenione", suspicious: "Podejrzane", no_analysis: "Do analizy",
};

// Zapamiętane sortowanie/filtr — bez nazywania, jeden slot na przeglądarkę (jak
// collection_name). Zapisany widok stosuje się automatycznie przy kolejnym wejściu.
const SAVED_VIEW_KEY = "collection_saved_view";
type SavedView = { sort: SortKey; filter: FilterKey };
function loadSavedView(): SavedView | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(SAVED_VIEW_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.sort === "string") return parsed as SavedView;
    return null;
  } catch {
    return null;
  }
}

export default function CollectionPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>(() => loadSavedView()?.sort ?? "newest");
  const [collectionName, setCollectionName] = useState("Moja kolekcja");
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("Moja kolekcja");
  const [showManualModal, setShowManualModal] = useState(false);

  const [activeFilter, setActiveFilter] = useState<FilterKey>(() => loadSavedView()?.filter ?? null);
  const [savedView, setSavedView] = useState<SavedView | null>(() => loadSavedView());
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOpen, setSortOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  // Feature 4: expanded groups for club mode
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  // Kliknięcie "Najdroższa" w Portfelu Koszulek — otwiera widok szczegółowy
  // tej konkretnej karty i przewija do niej (jeśli sortujemy po klubie,
  // trzeba też rozwinąć jej grupę, bo inaczej karta w ogóle nie jest w DOM).
  const [focusItemId, setFocusItemId] = useState<string | null>(null);

  function handleSelectItem(item: any) {
    if (sort === "club" && item.club) {
      setExpandedGroups((prev) => new Set(prev).add(item.club));
    }
    setFocusItemId(item.id);
    setTimeout(() => {
      document.getElementById(`collection-item-${item.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 50);
  }

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

  // Polling: odśwież kolekcję gdy są pozycje bez wyceny rynkowej
  useEffect(() => {
    if (loading) return;
    const hasPending = items.some(isPendingValuation);
    if (!hasPending) return;
    let polls = 0;
    const interval = setInterval(async () => {
      polls++;
      try {
        const fresh = await getCollection();
        setItems(fresh);
        if (!fresh.some(isPendingValuation) || polls >= 6) clearInterval(interval);
      } catch {
        clearInterval(interval);
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [loading, items.length]);

  // Feature 3: sort with expensive/cheap
  const sorted = [...items].sort((a, b) => {
    if (sort === "club") return (a.club || "").localeCompare(b.club || "");
    if (sort === "oldest") return new Date(a.added_at || 0).getTime() - new Date(b.added_at || 0).getTime();
    if (sort === "expensive") {
      const aVal = effectiveItemValue(a);
      const bVal = effectiveItemValue(b);
      if (aVal === null && bVal === null) return 0;
      if (aVal === null) return 1;
      if (bVal === null) return -1;
      return bVal - aVal;
    }
    if (sort === "cheap") {
      const aVal = effectiveItemValue(a);
      const bVal = effectiveItemValue(b);
      if (aVal === null && bVal === null) return 0;
      if (aVal === null) return 1;
      if (bVal === null) return -1;
      return aVal - bVal;
    }
    return new Date(b.added_at || 0).getTime() - new Date(a.added_at || 0).getTime();
  });

  const afterFilter = (() => {
    if (!activeFilter || activeFilter === "all") return sorted;
    if (activeFilter === "suspicious") return sorted.filter((i) => i.verdict_category === "podrobka");
    if (activeFilter === "valuated") return sorted.filter((i) => effectiveItemValue(i) != null);
    if (activeFilter === "no_analysis") return sorted.filter((i) => !i.report_id || i.is_manual);
    return sorted;
  })();

  const filtered = (() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return afterFilter;
    return afterFilter.filter((i) =>
      [i.club, i.player_name, i.season, i.brand]
        .filter(Boolean)
        .some((v: string) => v.toLowerCase().includes(q))
    );
  })();

  // Feature 4: group by club when sort === "club"
  const groupedClubs = (() => {
    if (sort !== "club") return [];
    const map = new Map<string, any[]>();
    for (const item of filtered) {
      const club = item.club || "Nieznany klub";
      if (!map.has(club)) map.set(club, []);
      map.get(club)!.push(item);
    }
    return Array.from(map.entries()).map(([club, items]) => ({ club, items }));
  })();

  // When switching to club sort, initialize expanded groups with first club
  useEffect(() => {
    if (sort === "club" && groupedClubs.length > 0) {
      setExpandedGroups(new Set([groupedClubs[0].club]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sort]);

  function toggleGroup(club: string) {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(club)) next.delete(club);
      else next.add(club);
      return next;
    });
  }

  const handleDelete = async (itemId: string) => {
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

  const handleItemUpdate = (updated: any) => {
    setItems((prev) => prev.map((i) => i.id === updated.id ? updated : i));
  };

  // Feature 1: handle filter click from tiles
  function handleTileFilter(filter: FilterKey) {
    setActiveFilter(filter);
    setTimeout(() => {
      listRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 50);
  }

  const isCurrentViewSaved = !!savedView && savedView.sort === sort && savedView.filter === activeFilter;

  function toggleSavedView() {
    if (isCurrentViewSaved) {
      localStorage.removeItem(SAVED_VIEW_KEY);
      setSavedView(null);
    } else {
      const next: SavedView = { sort, filter: activeFilter };
      localStorage.setItem(SAVED_VIEW_KEY, JSON.stringify(next));
      setSavedView(next);
    }
  }

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
        <div className="flex flex-col gap-0.5">
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
          {/* Feature 10: collection header stats */}
          {items.length > 0 && (
            <p className="text-xs text-muted-foreground">
              {pluralItems(items.length)}
              {items.filter((i) => i.verdict_category === "podrobka").length > 0 && (
                <> · <span className="text-red-400">{items.filter((i) => i.verdict_category === "podrobka").length} podejrzanych</span></>
              )}
              {items.filter((i) => i.verdict_category !== "podrobka" && i.verdict_category).length > 0 && (
                <> · <span className="text-emerald-400">{items.filter((i) => i.verdict_category !== "podrobka" && i.verdict_category).length} autentycznych</span></>
              )}
            </p>
          )}
        </div>
      </div>

      {items.length >= 1 && <PortfolioStats items={items} onSelectItem={handleSelectItem} />}

      <div className="flex items-center gap-2">
        <Link
          href="/analyze/form"
          className="inline-flex items-center justify-center gap-2 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400"
        >
          <Search className="h-3.5 w-3.5" />
          Nowa analiza
        </Link>
        <button
          onClick={() => setShowManualModal(true)}
          className="inline-flex items-center justify-center gap-1.5 rounded-full border border-slate-600/60 bg-slate-800/40 px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:border-emerald-400/40 hover:text-emerald-300"
        >
          <Plus className="h-3.5 w-3.5" />
          Dodaj koszulkę
        </button>
      </div>

      {items.length >= 1 && (
        <div className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Kolekcja</p>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Szukaj koszulki, klubu lub zawodnika"
              className="w-full rounded-xl border border-border/60 bg-slate-900/60 py-2 pl-8 pr-3 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-emerald-500/40 focus:ring-1 focus:ring-emerald-500/20"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Filter + Sort row */}
          <div className="flex items-center gap-2">
            {/* Filter dropdown */}
            <div className="relative">
              <button
                onClick={() => setFilterOpen((v) => !v)}
                className="flex items-center gap-1.5 rounded-full border border-border/60 bg-slate-900/40 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-slate-100"
              >
                <span className="text-slate-500">Filtr:</span>
                <span className="font-medium">{FILTER_LABELS[activeFilter ?? "all"]}</span>
                <ChevronDown className="h-3 w-3 text-slate-500" />
              </button>
              {filterOpen && (
                <>
                  <div className="fixed inset-0 z-20" onClick={() => setFilterOpen(false)} />
                  <div className="absolute left-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-xl border border-border/60 bg-slate-900 shadow-xl">
                    <p className="px-3 pt-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Filtruj według</p>
                    {(["all", "valuated", "suspicious", "no_analysis"] as const).map((key) => (
                      <button
                        key={key}
                        onClick={() => { handleTileFilter(key === "all" ? null : key); setFilterOpen(false); }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-slate-300 transition hover:bg-slate-800 hover:text-slate-100"
                      >
                        <span className="w-3 text-emerald-400">{(activeFilter ?? "all") === key ? "✓" : ""}</span>
                        {FILTER_LABELS[key]}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Sort dropdown */}
            {items.length > 1 && (
              <div className="relative">
                <button
                  onClick={() => setSortOpen((v) => !v)}
                  className="flex items-center gap-1.5 rounded-full border border-border/60 bg-slate-900/40 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-slate-100"
                >
                  <SlidersHorizontal className="h-3 w-3 text-slate-500" />
                  <span className="text-slate-500">Sortuj:</span>
                  <span className="font-medium">{SORT_LABELS[sort]}</span>
                  <ChevronDown className="h-3 w-3 text-slate-500" />
                </button>
                {sortOpen && (
                  <>
                    <div className="fixed inset-0 z-20" onClick={() => setSortOpen(false)} />
                    <div className="absolute left-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-xl border border-border/60 bg-slate-900 shadow-xl">
                      <p className="px-3 pt-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Sortuj według</p>
                      {(["newest", "oldest", "expensive", "cheap", "club"] as SortKey[]).map((key) => (
                        <button
                          key={key}
                          onClick={() => {
                            setSort(key);
                            setSortOpen(false);
                            if (key === "expensive" || key === "cheap") {
                              setTimeout(() => listRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
                            }
                          }}
                          className="flex w-full items-center gap-2 px-3 py-2 text-xs text-slate-300 transition hover:bg-slate-800 hover:text-slate-100"
                        >
                          <span className="w-3 text-emerald-400">{sort === key ? "✓" : ""}</span>
                          {SORT_LABELS[key]}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Zapisz obecny filtr+sortowanie jako swój domyślny widok — tylko ikona,
                żeby zmieściło się w rzędzie z Filtr/Sortuj bez zawijania */}
            <button
              onClick={toggleSavedView}
              aria-label={isCurrentViewSaved ? "Usuń zapisany widok" : "Zapisz ten widok jako domyślny"}
              title={isCurrentViewSaved ? "Usuń zapisany widok" : "Zapisz ten widok jako domyślny"}
              className={cn(
                "flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-full border transition",
                isCurrentViewSaved
                  ? "border-emerald-400/50 bg-emerald-500/10 text-emerald-300"
                  : "border-border/60 bg-slate-900/40 text-slate-300 hover:border-slate-500 hover:text-slate-100"
              )}
            >
              {isCurrentViewSaved ? <BookmarkCheck className="h-3.5 w-3.5" /> : <Bookmark className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      )}

      {error && <div className="glass-card p-4 text-sm text-red-300">{error}</div>}

      {items.length === 0 && !error && (
        <div className="glass-card flex flex-col items-center gap-4 p-10 text-center">
          <ShieldCheck className="h-10 w-10 text-slate-600" />
          <div>
            <p className="font-medium text-slate-300">Kolekcja jest pusta</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Sprawdź koszulkę i dodaj ją do kolekcji, albo dodaj ją ręcznie.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setShowManualModal(true)}
              className="rounded-full border border-slate-600/60 px-4 py-2 text-sm font-medium text-slate-300 transition hover:text-emerald-300"
            >
              Dodaj ręcznie
            </button>
            <Link
              href="/analyze/form"
              className="rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400"
            >
              Sprawdź koszulkę
            </Link>
          </div>
        </div>
      )}

      <div ref={listRef}>
        {/* Empty search state */}
        {searchQuery && filtered.length === 0 && (
          <div className="py-6 text-center text-sm text-slate-500">
            Nie znaleziono koszulek
            <button onClick={() => setSearchQuery("")} className="ml-2 text-slate-400 underline hover:text-slate-200">
              Wyczyść wyszukiwanie
            </button>
          </div>
        )}

        {/* Club grouping mode */}
        {sort === "club" && groupedClubs.length > 0 ? (
          <div className="flex flex-col gap-1">
            {groupedClubs.map(({ club, items: groupItems }) => (
              <div key={club} className="glass-card overflow-hidden">
                <button
                  onClick={() => toggleGroup(club)}
                  className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-slate-300 hover:text-slate-100"
                >
                  <span>
                    {club}{" "}
                    <span className="text-slate-500 text-xs">({groupItems.length})</span>
                  </span>
                  {expandedGroups.has(club)
                    ? <ChevronUp className="h-4 w-4" />
                    : <ChevronDown className="h-4 w-4" />
                  }
                </button>
                {expandedGroups.has(club) && (
                  <div className="grid grid-cols-2 gap-3 border-t border-border/30 p-3 sm:grid-cols-3 lg:grid-cols-4">
                    {groupItems.map((item) => (
                      <CollectionCard
                        key={item.id}
                        item={item}
                        onDelete={handleDelete}
                        onMarketValueRefresh={handleMarketValueRefresh}
                        onUpdate={handleItemUpdate}
                        autoOpen={focusItemId === item.id}
                        onAutoOpened={() => setFocusItemId(null)}
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          filtered.length > 0 && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {filtered.map((item) => (
                <CollectionCard
                  key={item.id}
                  item={item}
                  onDelete={handleDelete}
                  onMarketValueRefresh={handleMarketValueRefresh}
                  onUpdate={handleItemUpdate}
                  autoOpen={focusItemId === item.id}
                  onAutoOpened={() => setFocusItemId(null)}
                />
              ))}
            </div>
          )
        )}
      </div>

      {showManualModal && (
        <JerseyFormModal
          mode="add"
          onClose={() => setShowManualModal(false)}
          onSaved={(item) => {
            setItems((prev) => [item, ...prev]);
            setShowManualModal(false);
          }}
        />
      )}
    </div>
  );
}

// ── Portfolio Stats ───────────────────────────────────────────

function PortfolioStats({ items, onSelectItem }: { items: any[]; onSelectItem: (item: any) => void }) {
  const totalInvested = items.reduce((sum, i) => {
    if (!i.purchase_price) return sum;
    const price = parseFloat(String(i.purchase_price).replace(",", "."));
    if (isNaN(price)) return sum;
    return sum + price * (FX_TO_PLN[(i.purchase_currency || "PLN").toUpperCase()] ?? 1);
  }, 0);

  const totalMarket = items.reduce((sum, i) => sum + (effectiveItemValue(i) ?? 0), 0);
  const itemsWithMarket = items.filter((i) => effectiveItemValue(i) != null).length;
  const itemsWithPrice = items.filter((i) => i.purchase_price).length;
  const gain = totalMarket > 0 && totalInvested > 0 ? totalMarket - totalInvested : null;
  const roi = gain != null && totalInvested > 0 ? (gain / totalInvested) * 100 : null;
  const fmt = (n: number) => Math.round(n).toLocaleString("pl-PL");

  const mostExpensiveEntry = items.reduce(
    (best: { item: any; value: number } | null, i) => {
      const v = effectiveItemValue(i);
      if (v == null) return best;
      if (!best || v > best.value) return { item: i, value: v };
      return best;
    },
    null
  );
  const mostExpensive = mostExpensiveEntry?.item ?? null;

  return (
    <div className="space-y-2">
      {itemsWithMarket > 0 ? (
        <div className="glass-card space-y-3 p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Portfel Koszulek · wartość rynkowa</p>
          <div>
            <p className="text-3xl font-bold tracking-tight text-emerald-300">{fmt(totalMarket)} PLN</p>
            <p className="mt-0.5 text-xs text-slate-500">wycena {itemsWithMarket} z {items.length} koszulek</p>
          </div>
          {gain != null && (
            <p className={cn("flex items-center gap-1 text-sm font-semibold", gain >= 0 ? "text-emerald-400" : "text-red-400")}>
              {gain >= 0 ? <TrendingUp className="h-3.5 w-3.5 shrink-0" /> : <TrendingDown className="h-3.5 w-3.5 shrink-0" />}
              <span>{gain >= 0 ? "+" : ""}{fmt(gain)} PLN{roi != null && <span className="font-medium opacity-75"> ({roi >= 0 ? "+" : ""}{roi.toFixed(1)}%)</span>}</span>
            </p>
          )}
          {(totalInvested > 0 || mostExpensive) && (
            <div className="grid grid-cols-2 gap-3 border-t border-border/30 pt-3">
              {totalInvested > 0 && (
                <div>
                  <p className="text-[11px] text-slate-500">Zainwestowano</p>
                  <p className="mt-0.5 text-sm font-semibold text-slate-200">{fmt(totalInvested)} PLN</p>
                </div>
              )}
              {mostExpensive && (
                <button
                  onClick={() => onSelectItem(mostExpensive)}
                  className="min-w-0 rounded-lg text-left transition hover:opacity-80"
                >
                  <p className="truncate text-[11px] text-slate-500">
                    Najdroższa{mostExpensive.club ? ` · ${mostExpensive.club}` : ""}
                  </p>
                  <p className="mt-0.5 text-sm font-semibold text-emerald-300 underline underline-offset-2">
                    ~{fmt(mostExpensiveEntry?.value ?? 0)} PLN
                  </p>
                </button>
              )}
            </div>
          )}
        </div>
      ) : (
        totalInvested > 0 && (
          <div className="glass-card flex flex-col items-center gap-1 p-5 text-center">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Portfel Koszulek</p>
            <p className="text-3xl font-bold tracking-tight text-slate-100">{fmt(totalInvested)} PLN</p>
            <p className="text-xs text-slate-500">zainwestowano · {itemsWithPrice} z {items.length} koszulek z ceną</p>
          </div>
        )
      )}
    </div>
  );
}

// ── Jersey Thumbnail ──────────────────────────────────────────

function JerseyThumbnail({ item }: { item: any }) {
  const [imgError, setImgError] = useState(false);
  const isRisky = item.verdict_category === "podrobka";
  const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");

  // Manual z własnym zdjęciem lub analyzed z case_id
  const src = item.has_photo
    ? getCollectionThumbnailUrl(item.id)
    : item.case_id && !item.is_manual
    ? `${apiBase}/api/cases/${item.case_id}/thumbnail`
    : null;

  // Widok ogólny (karta w siatce) — miniatura, przycięta do jednego kształtu
  const wrapperClass = "relative w-full overflow-hidden border-b border-white/5 aspect-[4/3]";

  if (src && !imgError) {
    return (
      <div className={wrapperClass}>
        <img src={src} alt="" onError={() => setImgError(true)} className="h-full w-full object-cover" />
      </div>
    );
  }

  return (
    <div className={cn(wrapperClass, "flex items-center justify-center", isRisky ? "bg-red-950/40" : "bg-slate-800/60")}>
      <svg viewBox="0 0 44 64" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-16 w-11 opacity-70">
        <path d="M8 8 L4 18 L12 20 L12 56 L32 56 L32 20 L40 18 L36 8 L28 12 Q22 15 16 12 Z"
          fill={isRisky ? "rgba(239,68,68,0.15)" : "rgba(16,185,129,0.12)"}
          stroke={isRisky ? "rgba(239,68,68,0.4)" : "rgba(16,185,129,0.35)"}
          strokeWidth="1.2" strokeLinejoin="round" />
        <path d="M16 12 Q22 17 28 12" stroke={isRisky ? "rgba(239,68,68,0.5)" : "rgba(16,185,129,0.5)"} strokeWidth="1.2" fill="none" strokeLinecap="round" />
      </svg>
    </div>
  );
}

// Widok szczegółowy: całe zdjęcie widoczne (object-contain, bez przycinania) na
// ciemnym tle z poświatą; jeśli jest drugie zdjęcie (manual: photo_path_2, analyzed:
// drugie wgrane zdjęcie z case'a), można przełączać swipe'em lub kropkami.
// Uwaga: imgError resetuje się tylko po zmianie index/src2, nie po item.id — bezpieczne
// dopóki komponent mountuje się na nowo przy każdym otwarciu modala (obecny call site),
// ale przy ewentualnym reużyciu jako trwały pager między pozycjami dodaj item.id do zależności.
function HeroPhotoCarousel({ item }: { item: any }) {
  const isRisky = item.verdict_category === "podrobka";
  const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");

  const src1 = item.has_photo
    ? getCollectionThumbnailUrl(item.id, 1)
    : item.case_id && !item.is_manual
    ? `${apiBase}/api/cases/${item.case_id}/thumbnail?index=0`
    : null;
  const src2 = item.has_photo
    ? (item.has_photo_2 ? getCollectionThumbnailUrl(item.id, 2) : null)
    : item.case_id && !item.is_manual
    ? `${apiBase}/api/cases/${item.case_id}/thumbnail?index=1`
    : null;

  const [index, setIndex] = useState(0);
  const [hasSecond, setHasSecond] = useState(false);
  const [imgError, setImgError] = useState(false);
  const touchStartX = useRef<number | null>(null);

  useEffect(() => {
    setImgError(false);
  }, [index]);

  useEffect(() => {
    setIndex(0);
    setImgError(false);
    if (!src2) { setHasSecond(false); return; }
    let cancelled = false;
    const probe = new window.Image();
    probe.onload = () => { if (!cancelled) setHasSecond(true); };
    probe.onerror = () => { if (!cancelled) setHasSecond(false); };
    probe.src = src2;
    return () => { cancelled = true; };
  }, [src2]);

  function onTouchStart(e: React.TouchEvent) {
    touchStartX.current = e.touches[0].clientX;
  }
  function onTouchEnd(e: React.TouchEvent) {
    if (touchStartX.current == null) return;
    const dx = e.changedTouches[0].clientX - touchStartX.current;
    touchStartX.current = null;
    if (Math.abs(dx) < 40) return;
    if (dx < 0 && hasSecond) setIndex(1);
    if (dx > 0) setIndex(0);
  }

  const activeSrc = index === 0 ? src1 : src2;
  const wrapperClass = cn(
    "relative flex w-full items-center justify-center overflow-hidden py-7 select-none",
    "bg-[radial-gradient(circle_at_50%_15%,rgba(16,185,129,0.18),transparent_60%),linear-gradient(to_bottom,#020617,#0b1120)]"
  );

  return (
    <div
      className={cn(wrapperClass, !activeSrc || imgError ? "min-h-[220px]" : undefined)}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      {activeSrc && !imgError ? (
        <img
          key={activeSrc}
          src={activeSrc}
          alt=""
          onError={() => setImgError(true)}
          className="max-h-[55vh] w-auto max-w-full object-contain drop-shadow-[0_18px_35px_rgba(0,0,0,0.55)]"
        />
      ) : (
        <svg viewBox="0 0 44 64" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-28 w-auto opacity-70">
          <path d="M8 8 L4 18 L12 20 L12 56 L32 56 L32 20 L40 18 L36 8 L28 12 Q22 15 16 12 Z"
            fill={isRisky ? "rgba(239,68,68,0.15)" : "rgba(16,185,129,0.12)"}
            stroke={isRisky ? "rgba(239,68,68,0.4)" : "rgba(16,185,129,0.35)"}
            strokeWidth="1.2" strokeLinejoin="round" />
          <path d="M16 12 Q22 17 28 12" stroke={isRisky ? "rgba(239,68,68,0.5)" : "rgba(16,185,129,0.5)"} strokeWidth="1.2" fill="none" strokeLinecap="round" />
        </svg>
      )}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-slate-950 to-transparent" />
      {hasSecond && (
        <div className="absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5">
          {[0, 1].map((i) => (
            <button
              key={i}
              onClick={() => setIndex(i)}
              aria-label={`Zdjęcie ${i + 1}`}
              className={cn(
                "h-1.5 rounded-full transition-all",
                index === i ? "w-5 bg-emerald-400" : "w-1.5 bg-white/40"
              )}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Collection Card ───────────────────────────────────────────
// Formularz edycji (z blokadą pól uzupełnionych przez AI) mieszka teraz w
// JerseyFormModal — reużywanym też do dodawania nowej koszulki ręcznie.

function CollectionCard({
  item,
  onDelete,
  onMarketValueRefresh,
  onUpdate,
  autoOpen,
  onAutoOpened,
}: {
  item: any;
  onDelete: (id: string) => void;
  onMarketValueRefresh: (id: string, result: any) => void;
  onUpdate: (item: any) => void;
  autoOpen?: boolean;
  onAutoOpened?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [valuating, setValuating] = useState(false);
  const [noDataAfterRefresh, setNoDataAfterRefresh] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Otwiera widok szczegółowy z zewnątrz (np. kliknięcie "Najdroższa" w
  // Portfelu Koszulek) — patrz handleSelectItem w CollectionPage.
  useEffect(() => {
    if (autoOpen) {
      setExpanded(true);
      onAutoOpened?.();
    }
  }, [autoOpen, onAutoOpened]);

  const vm = VERDICT_META[item.verdict_category] ?? {
    label: item.verdict_category ?? "—",
    bg: "bg-slate-500/20",
    text: "text-slate-300",
  };
  const purchasePln = (() => {
    if (!item.purchase_price) return null;
    const price = parseFloat(String(item.purchase_price).replace(",", "."));
    if (isNaN(price)) return null;
    return price * (FX_TO_PLN[(item.purchase_currency || "PLN").toUpperCase()] ?? 1);
  })();
  // Podróbki nie mają sprawdzanej wartości rynkowej (nie ma sensu jej
  // szukać) — w jej miejsce pokazujemy cenę zakupu, jeśli user ją podał
  // (effectiveItemValue robi dokładnie to samo podstawienie co w PortfolioStats
  // i w sortowaniu/filtrowaniu listy — jedno miejsce prawdy).
  const isFake = item.verdict_category === "podrobka";
  const marketValue: number | null = effectiveItemValue(item);
  const gainPln = !isFake && purchasePln != null && marketValue != null ? marketValue - purchasePln : null;

  async function handleValuate() {
    setValuating(true);
    setNoDataAfterRefresh(false);
    try {
      const result = await refreshMarketValue(item.id);
      onMarketValueRefresh(item.id, result);
      if ((result?.market_value_result?.matched_count ?? result?.market_value_sample_size ?? 0) === 0) {
        setNoDataAfterRefresh(true);
      }
    } catch {
      // ignoruj — user widzi brak wartości
    } finally {
      setValuating(false);
    }
  }

  const isAnalyzed = !item.is_manual && item.report_id;
  // Złoty akcent tylko dla realnie zweryfikowanych, autentycznych sztuk —
  // dla podróbki odznaka LS zostaje neutralna (złoto sugerowałoby "premium",
  // co byłoby mylące przy oznaczeniu fałszywki).
  const isGenuineVerified = Boolean(isAnalyzed) && Boolean(item.verdict_category) && item.verdict_category !== "podrobka";

  function closeExpanded() {
    setExpanded(false);
  }

  return (
    <div id={`collection-item-${item.id}`} className={cn("glass-card overflow-hidden", isGenuineVerified && "ring-1 ring-amber-400/40")}>
      {/* Widok ogólny (karta w siatce) — tylko podgląd; zmiana danych/zdjęcia
          wyłącznie przez osobny popup edycji (ikonka Edytuj) */}
      <div className="relative">
        <JerseyThumbnail item={item} />

        <div className="absolute left-2 top-2 flex items-center gap-1">
          <button
            onClick={(e) => { e.stopPropagation(); setShowEditModal(true); }}
            className="rounded-full bg-slate-950/80 p-1.5 text-slate-300 backdrop-blur transition hover:text-emerald-400"
            aria-label="Edytuj"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); setConfirmDelete(true); }}
            className="rounded-full bg-slate-950/80 p-1.5 text-slate-300 backdrop-blur transition hover:text-red-400"
            aria-label="Usuń z kolekcji"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="absolute right-2 top-2 flex items-center gap-1">
          {isAnalyzed && (
            <span className={cn(
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide shadow",
              isGenuineVerified
                ? "bg-gradient-to-br from-amber-300 to-amber-500 text-amber-950"
                : "bg-slate-950/80 text-emerald-400 backdrop-blur"
            )}>
              <ShieldCheck className="h-2.5 w-2.5" />
              LS
            </span>
          )}
          {item.is_manual && (
            <span className="inline-flex items-center rounded-full bg-slate-950/80 px-2 py-0.5 text-[10px] font-medium text-slate-300 backdrop-blur">
              ręcznie
            </span>
          )}
        </div>

        {item.verdict_category && (
          <span className="absolute bottom-2 left-2 rounded-full bg-slate-950/85 px-2.5 py-1 text-xs font-semibold backdrop-blur">
            <span className={vm.text}>{vm.short}</span>
          </span>
        )}
      </div>

      {/* Karta zawsze zostaje na swoim miejscu w siatce — szczegóły otwierają się w oknie na wierzchu, żeby siatka się nie przestawiała */}
      <div className="p-3">
        <p className="line-clamp-2 text-base font-semibold leading-snug text-slate-100">
          {item.club || "Nieznany klub"}
        </p>

        {(item.player_name || item.player_number) && (
          <p className="mt-0.5 truncate text-sm font-medium leading-tight text-slate-300">
            {item.player_name}{item.player_number ? ` #${item.player_number}` : ""}
          </p>
        )}

        {(item.brand || item.season) && (
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {[item.brand, fmtSeason(item.season)].filter(Boolean).join(" · ")}
          </p>
        )}

        {marketValue != null && (
          <div className="mt-2">
            <span className="text-base font-semibold text-emerald-300">
              ~{Math.round(marketValue).toLocaleString("pl-PL")} PLN
            </span>
          </div>
        )}

        <div className="mt-1.5 flex justify-end">
          <button
            onClick={() => setExpanded(true)}
            className="flex shrink-0 items-center gap-1 text-xs font-medium text-emerald-500 transition hover:text-emerald-400"
          >
            Szczegóły
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Delete confirmation modal — portal do document.body: karta ma backdrop-blur (glass-card),
          które w WebKit tworzy własny containing block dla position:fixed, więc bez portalu ten
          popup renderował się wciśnięty (i przycięty przez overflow-hidden) w miejsce małej karty
          zamiast pokrywać cały ekran — na Safari wyglądało to jak "klik w kosz nic nie robi". */}
      {confirmDelete && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4" onClick={() => setConfirmDelete(false)}>
          <div className="glass-card w-full max-w-sm space-y-4 rounded-2xl p-6" onClick={(e) => e.stopPropagation()}>
            <p className="text-sm font-medium text-slate-100">
              Na pewno usunąć {item.club || "tę koszulkę"} z kolekcji?
            </p>
            <p className="text-xs text-slate-400">
              Będziesz mógł dodać ją ponownie później — z poziomu nowej analizy albo ręcznie — ale stracisz zapisaną wycenę i historię cen tej pozycji.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => { setConfirmDelete(false); onDelete(item.id); }}
                className="flex-1 rounded-full bg-red-500/80 py-2 text-sm font-medium text-white transition hover:bg-red-500"
              >
                Usuń
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="flex-1 rounded-full border border-slate-600/60 py-2 text-sm font-medium text-slate-300 transition hover:text-slate-100"
              >
                Anuluj
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Widok szczegółowy — okno "na froncie" nad całą siatką; karta w siatce nigdy się nie przesuwa.
          Portal do document.body: karta ma backdrop-blur (glass-card), które w WebKit tworzy własny
          containing block dla position:fixed — bez portalu okno renderowało się wciśnięte w miejsce
          karty zamiast pokrywać cały ekran. */}
      {expanded && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8"
          onClick={closeExpanded}
        >
          <div className={cn("glass-card w-full max-w-md overflow-hidden", isGenuineVerified && "ring-1 ring-amber-400/40")} onClick={(e) => e.stopPropagation()}>
            <div className="relative">
              <HeroPhotoCarousel item={item} />
              <div className="absolute right-3 top-3 flex items-center gap-1.5">
                {isAnalyzed && (
                  <span className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide shadow-lg shadow-black/30",
                    isGenuineVerified
                      ? "bg-gradient-to-br from-amber-300 to-amber-500 text-amber-950"
                      : "border border-emerald-400/30 bg-slate-950/80 text-emerald-400 backdrop-blur"
                  )}>
                    <ShieldCheck className="h-3 w-3" />
                    LS
                  </span>
                )}
                {item.is_manual && (
                  <span className="inline-flex items-center rounded-full border border-white/10 bg-slate-950/80 px-2.5 py-1 text-[10px] font-medium text-slate-300 shadow-lg shadow-black/30 backdrop-blur">
                    ręcznie
                  </span>
                )}
              </div>
              {item.verdict_category && (
                <span className={cn(
                  "absolute bottom-3 left-3 inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-bold shadow-lg shadow-black/40 backdrop-blur",
                  vm.bg, vm.text
                )}>
                  <ShieldCheck className="h-4 w-4" />
                  {vm.short}
                </span>
              )}
            </div>

            <div className="space-y-3 p-4 pb-5">
              {/* Nazwa + edytuj/usuń/zwiń — tak jak dawniej, nie na zdjęciu */}
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-xl font-semibold leading-snug text-slate-100">
                    {item.club || "Nieznany klub"}
                  </p>
                  {(item.player_name || item.player_number) && (
                    <p className="mt-0.5 text-sm font-medium leading-tight text-slate-300">
                      {item.player_name}{item.player_number ? ` #${item.player_number}` : ""}
                    </p>
                  )}
                  {(item.brand || item.season) && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {[item.brand, fmtSeason(item.season)].filter(Boolean).join(" · ")}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-0.5 -mr-1 -mt-0.5">
                  <button
                    onClick={() => setShowEditModal(true)}
                    className="rounded-full p-1.5 text-slate-600 transition hover:text-emerald-400"
                    aria-label="Edytuj"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => setConfirmDelete(true)}
                    className="rounded-full p-1.5 text-slate-600 transition hover:text-red-400"
                    aria-label="Usuń z kolekcji"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={closeExpanded}
                    className="rounded-full p-1.5 text-slate-600 transition hover:text-slate-200"
                    aria-label="Zwiń"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              {/* Wartość rynkowa + zysk/strata + cena zakupu — pełny widok */}
              {marketValue != null && (
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] uppercase tracking-wide text-slate-500">
                      {isFake ? "Wartość (cena zakupu)" : "Szacunkowa wartość"}
                    </p>
                    {!isFake && (
                      <button
                        onClick={handleValuate}
                        disabled={valuating}
                        aria-label="Odśwież wycenę"
                        title="Odśwież wycenę"
                        className="rounded-full p-1 text-slate-400 transition hover:text-emerald-300 disabled:opacity-50"
                      >
                        <RefreshCw className={cn("h-3.5 w-3.5", valuating && "animate-spin")} />
                      </button>
                    )}
                  </div>
                  <div className="mt-0.5 flex items-baseline gap-2">
                  <span className="text-base font-semibold text-emerald-300">
                    ~{Math.round(marketValue).toLocaleString("pl-PL")} PLN
                  </span>
                  {gainPln != null && (
                    <span className={cn(
                      "flex items-center gap-0.5 text-xs font-medium",
                      gainPln >= 0 ? "text-emerald-400" : "text-red-400"
                    )}>
                      {gainPln >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                      {gainPln >= 0 ? "+" : ""}{Math.round(gainPln).toLocaleString("pl-PL")} PLN
                    </span>
                  )}
                  </div>
                  {!isFake && item.market_value_range_min != null && item.market_value_range_max != null && (
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      Widełki: {Math.round(item.market_value_range_min).toLocaleString("pl-PL")}–{Math.round(item.market_value_range_max).toLocaleString("pl-PL")} PLN
                    </p>
                  )}
                  {!isFake && item.market_value_updated_at && (
                    <p className="mt-0.5 text-[11px] text-slate-600">
                      Wycena: {new Date(item.market_value_updated_at).toLocaleDateString("pl-PL")}
                      {item.market_value_sample_size ? ` · ${item.market_value_sample_size} aukcji` : ""}
                    </p>
                  )}
                  {!isFake && marketValueConfidenceLabel(item.market_value_confidence) && (
                    <p className="mt-0.5 text-[11px] font-medium text-amber-400/90">
                      {marketValueConfidenceLabel(item.market_value_confidence)}
                    </p>
                  )}
                  <p className="mt-1 text-[10px] leading-snug text-slate-600">
                    {isFake
                      ? "Podróbek nie wyceniamy na aukcjach — to cena, którą podałeś przy zakupie."
                      : "Ceny ofertowe z ogłoszeń, nie ceny faktycznej sprzedaży — realna cena transakcji może się różnić."}
                  </p>
                </div>
              )}
              {item.purchase_price && (
                <p className="text-xs text-slate-500">
                  Cena zakupu: {item.purchase_price} {item.purchase_currency || "PLN"}
                </p>
              )}

              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                {item.model_type && (
                  <>
                    <dt className="text-slate-500">Model</dt>
                    <dd className="text-slate-300">{item.model_type}</dd>
                  </>
                )}
                {item.purchase_date && (
                  <>
                    <dt className="text-slate-500">Data zakupu</dt>
                    <dd className="text-slate-300">{new Date(item.purchase_date).toLocaleDateString("pl-PL")}</dd>
                  </>
                )}
                {item.purchase_source && (
                  <>
                    <dt className="text-slate-500">Źródło zakupu</dt>
                    <dd className="text-slate-300">{item.purchase_source}</dd>
                  </>
                )}
                {item.sku && (
                  <>
                    <dt className="text-slate-500">SKU</dt>
                    <dd className="font-mono text-slate-300">{item.sku}</dd>
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
                {isAnalyzed && (
                  <Link
                    href={`/case/${item.case_id}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/50 bg-emerald-500/10 px-4 py-2 text-xs font-medium text-emerald-200 transition hover:bg-emerald-500/20"
                  >
                    Zobacz pełny raport →
                  </Link>
                )}
                {isFake ? null : noDataAfterRefresh ? (
                  <span className="inline-flex items-center gap-2 text-xs text-slate-500">
                    Brak aktywnych aukcji dla tej koszulki
                    <button
                      onClick={handleValuate}
                      disabled={valuating}
                      className="text-slate-400 underline underline-offset-2 hover:text-slate-300 disabled:opacity-50"
                    >
                      {valuating ? "Szacuję..." : "Sprawdź ponownie"}
                    </button>
                  </span>
                ) : marketValue == null && item.market_value_updated_at ? (
                  <span className="inline-flex items-center gap-2 text-xs text-slate-500">
                    Brak danych rynkowych
                    <button
                      onClick={handleValuate}
                      disabled={valuating}
                      className="text-slate-400 underline underline-offset-2 hover:text-slate-300 disabled:opacity-50"
                    >
                      {valuating ? "Szacuję..." : "Sprawdź ponownie"}
                    </button>
                  </span>
                ) : marketValue == null ? (
                  // marketValue != null: przycisk odświeżenia jest już przy "Szacunkowa
                  // wartość" wyżej — nie duplikujemy go tutaj.
                  <button
                    onClick={handleValuate}
                    disabled={valuating}
                    className="inline-flex items-center gap-1.5 rounded-full border border-slate-600/60 bg-slate-800/40 px-4 py-2 text-xs font-medium text-slate-300 transition hover:border-emerald-400/40 hover:text-emerald-300 disabled:opacity-50"
                  >
                    <RefreshCw className={cn("h-3 w-3", valuating && "animate-spin")} />
                    {valuating ? "Szacuję..." : "Sprawdź wartość rynkową"}
                  </button>
                ) : null}
                {/* marketValue != null: ta sama informacja jest już pokazana wyżej,
                    obok "Szacunkowa wartość" — nie dublujemy jej tutaj. */}
                {!isFake && marketValue == null && item.market_value_updated_at && !noDataAfterRefresh && (
                  <span className="self-center text-[11px] text-slate-600">
                    Wycena: {new Date(item.market_value_updated_at).toLocaleDateString("pl-PL")}
                    {item.market_value_sample_size ? ` · ${item.market_value_sample_size} aukcji` : ""}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Edycja — ten sam popup co dodawanie nowej koszulki (JerseyFormModal),
          żeby mieć jeden komponent, jedną zasadę zamykania i jedno miejsce do
          utrzymania zamiast osobnego, zagnieżdżonego formularza w tym widoku. */}
      {showEditModal && createPortal(
        <JerseyFormModal
          mode="edit"
          item={item}
          onClose={() => setShowEditModal(false)}
          onSaved={(updated) => { onUpdate(updated); setShowEditModal(false); }}
        />,
        document.body
      )}
    </div>
  );
}
