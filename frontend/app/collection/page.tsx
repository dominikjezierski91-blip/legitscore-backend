"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";
import { getCollection, deleteFromCollection } from "@/lib/api";
import { Loader2, Trash2, ShieldCheck, Search } from "lucide-react";
import { cn } from "@/lib/utils";

const VERDICT_LABELS: Record<string, string> = {
  oryginalna_sklepowa: "Oryginalna (sklepowa)",
  meczowa: "Meczowa",
  oficjalna_replika: "Oficjalna replika",
  podrobka: "Podróbka",
  edycja_limitowana: "Edycja limitowana",
  treningowa_custom: "Treningowa / custom",
};

export default function CollectionPage() {
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login?next=/collection");
      return;
    }
    getCollection()
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [user, authLoading, router]);

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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-50">
            Moja kolekcja
          </h1>
          <p className="mt-0.5 text-xs text-muted-foreground">{user.email}</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/analyze"
            className="inline-flex items-center gap-2 rounded-full bg-emerald-500 px-4 py-2 text-xs font-medium text-slate-950 transition hover:bg-emerald-400"
          >
            <Search className="h-3.5 w-3.5" />
            Sprawdź kolejną koszulkę
          </Link>
          <button
            onClick={logout}
            className="rounded-full border border-slate-600 px-3 py-2 text-xs text-slate-400 transition hover:border-slate-500 hover:text-slate-300"
          >
            Wyloguj
          </button>
        </div>
      </div>

      {error && (
        <div className="glass-card p-4 text-sm text-red-300">{error}</div>
      )}

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

      {items.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <CollectionCard key={item.id} item={item} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  );
}

function CollectionCard({ item, onDelete }: { item: any; onDelete: (id: string) => void }) {
  const verdictLabel = VERDICT_LABELS[item.verdict_category] ?? item.verdict_category ?? "—";
  const isRisky = item.verdict_category === "podrobka";

  return (
    <div className="glass-card flex flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-slate-100">
            {item.club || "Nieznany klub"}
          </p>
          <p className="text-xs text-muted-foreground">
            {item.season || "—"}{item.brand ? ` · ${item.brand}` : ""}
          </p>
        </div>
        <button
          onClick={() => onDelete(item.id)}
          className="shrink-0 rounded-full p-1.5 text-slate-600 transition hover:text-red-400"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {item.player_name && (
        <p className="text-xs text-slate-400">
          {item.player_name}{item.player_number ? ` #${item.player_number}` : ""}
        </p>
      )}

      <div className="flex items-center gap-2 text-xs">
        <span
          className={cn(
            "rounded-full px-2 py-0.5 font-medium",
            isRisky
              ? "bg-red-500/20 text-red-300"
              : "bg-emerald-500/20 text-emerald-300"
          )}
        >
          {verdictLabel}
        </span>
        {item.confidence_percent != null && (
          <span className="text-slate-500">{item.confidence_percent}%</span>
        )}
      </div>

      {item.sku && (
        <p className="text-[10px] font-mono text-slate-500">SKU: {item.sku}</p>
      )}

      <div className="flex items-center justify-between border-t border-border/40 pt-2 text-[10px] text-slate-600">
        <span>{item.added_at ? new Date(item.added_at).toLocaleDateString("pl-PL") : "—"}</span>
        <Link href={`/case/${item.case_id}`} className="text-emerald-600 hover:text-emerald-400">
          Zobacz raport →
        </Link>
      </div>
    </div>
  );
}
