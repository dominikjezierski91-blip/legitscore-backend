"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/auth-provider";
import { addToCollection, type CollectionItemPayload } from "@/lib/api";
import { X, BookmarkPlus, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  caseId: string;
  mode?: string;
  reportData: any;
  onClose: () => void;
  onSaved?: () => void;
};

export function AddToCollectionModal({ caseId, mode, reportData, onClose, onSaved }: Props) {
  const { user } = useAuth();
  const router = useRouter();

  const subject = reportData?.subject ?? {};
  const verdict = reportData?.verdict ?? {};

  const [purchasePrice, setPurchasePrice] = useState("");
  const [purchaseCurrency, setPurchaseCurrency] = useState("PLN");
  const [purchaseDate, setPurchaseDate] = useState("");
  const [purchaseSource, setPurchaseSource] = useState("");
  const [notes, setNotes] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  if (!user) {
    return (
      <ModalShell onClose={onClose}>
        <div className="space-y-4 text-center">
          <BookmarkPlus className="mx-auto h-10 w-10 text-emerald-400" />
          <div>
            <h2 className="text-lg font-semibold text-slate-50">
              Zaloguj się, aby dodać do kolekcji
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Zaloguj się lub załóż konto, aby zapisać tę koszulkę w swojej kolekcji.
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => router.push(`/login?next=${encodeURIComponent(`/case/${caseId}?add_to_collection=1`)}`)}
              className="w-full rounded-full bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400"
            >
              Zaloguj się
            </button>
            <button
              onClick={() => router.push(`/register?next=${encodeURIComponent(`/case/${caseId}?add_to_collection=1`)}`)}
              className="w-full rounded-full border border-emerald-400/60 bg-emerald-500/10 px-4 py-2.5 text-sm font-medium text-emerald-200 transition hover:bg-emerald-500/20"
            >
              Załóż konto
            </button>
          </div>
        </div>
      </ModalShell>
    );
  }

  if (success) {
    return (
      <ModalShell onClose={onClose}>
        <div className="space-y-4 text-center">
          <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-400" />
          <div>
            <h2 className="text-lg font-semibold text-slate-50">Dodano do kolekcji</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Koszulka została zapisana w Twojej kolekcji.
            </p>
          </div>
          <button
            onClick={() => router.push("/collection")}
            className="w-full rounded-full bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400"
          >
            Zobacz kolekcję
          </button>
          <button onClick={onClose} className="w-full text-xs text-muted-foreground hover:text-slate-300">
            Zamknij
          </button>
        </div>
      </ModalShell>
    );
  }

  const handleSave = async () => {
    setError(null);
    setLoading(true);
    try {
      const payload: CollectionItemPayload = {
        case_id: caseId,
        report_mode: mode || "basic",
        club: subject.club || undefined,
        season: subject.season || undefined,
        model_type: subject.model || undefined,
        brand: subject.brand || undefined,
        player_name: subject.player_name || undefined,
        player_number: subject.player_number || undefined,
        verdict_category: verdict.verdict_category || undefined,
        confidence_percent: verdict.confidence_percent ?? undefined,
        confidence_level: verdict.confidence_level || undefined,
        sku: reportData?.decision_matrix
          ? undefined
          : (reportData?.sku || undefined),
        report_id: reportData?.report_id || undefined,
        analysis_date: reportData?.analysis_date || undefined,
        purchase_price: purchasePrice || undefined,
        purchase_currency: purchaseCurrency || undefined,
        purchase_date: purchaseDate || undefined,
        purchase_source: purchaseSource || undefined,
        notes: notes || undefined,
      };
      await addToCollection(payload);
      setSuccess(true);
      onSaved?.();
    } catch (err: any) {
      setError(err.message || "Nie udało się zapisać do kolekcji.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalShell onClose={onClose}>
      <div className="space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-slate-50">Dodaj do kolekcji</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Dane z raportu zostaną zapisane automatycznie. Pola poniżej są opcjonalne.
          </p>
        </div>

        {/* Podgląd danych z raportu */}
        <div className="rounded-xl border border-border/50 bg-slate-900/40 p-3 text-xs space-y-1 text-slate-300">
          {subject.club && <div><span className="text-slate-500">Klub:</span> {subject.club}</div>}
          {subject.season && <div><span className="text-slate-500">Sezon:</span> {subject.season}</div>}
          {subject.player_name && (
            <div><span className="text-slate-500">Zawodnik:</span> {subject.player_name} {subject.player_number ? `#${subject.player_number}` : ""}</div>
          )}
          {verdict.verdict_category && (
            <div><span className="text-slate-500">Kategoria:</span> {verdict.verdict_category}</div>
          )}
          {verdict.confidence_percent != null && (
            <div><span className="text-slate-500">Pewność:</span> {verdict.confidence_percent}%</div>
          )}
        </div>

        {/* Pola usera */}
        <div className="space-y-3">
          <div className="flex gap-2">
            <div className="flex-1 space-y-1">
              <label className="text-xs text-slate-400">Cena zakupu</label>
              <input
                type="text"
                value={purchasePrice}
                onChange={(e) => setPurchasePrice(e.target.value)}
                placeholder="np. 250"
                className="w-full rounded-lg border border-border/50 bg-slate-900/50 px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-emerald-500/50"
              />
            </div>
            <div className="w-20 space-y-1">
              <label className="text-xs text-slate-400">Waluta</label>
              <select
                value={purchaseCurrency}
                onChange={(e) => setPurchaseCurrency(e.target.value)}
                className="w-full rounded-lg border border-border/50 bg-slate-900/50 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-emerald-500/50"
              >
                <option>PLN</option>
                <option>EUR</option>
                <option>GBP</option>
                <option>USD</option>
              </select>
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-400">Data zakupu</label>
            <input
              type="date"
              value={purchaseDate}
              onChange={(e) => setPurchaseDate(e.target.value)}
              className="w-full rounded-lg border border-border/50 bg-slate-900/50 px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-emerald-500/50"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-400">Źródło zakupu</label>
            <input
              type="text"
              value={purchaseSource}
              onChange={(e) => setPurchaseSource(e.target.value)}
              placeholder="np. Vinted, eBay, sklep stacjonarny"
              className="w-full rounded-lg border border-border/50 bg-slate-900/50 px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-emerald-500/50"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-400">Notatki</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Opcjonalne notatki..."
              className="w-full rounded-lg border border-border/50 bg-slate-900/50 px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-emerald-500/50 resize-none"
            />
          </div>
        </div>

        {error && (
          <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>
        )}

        <div className="flex gap-2">
          <button
            onClick={handleSave}
            disabled={loading}
            className="flex-1 rounded-full bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400 disabled:opacity-60"
          >
            {loading ? "Zapisywanie..." : "Zapisz do kolekcji"}
          </button>
          <button
            onClick={onClose}
            className="rounded-full border border-slate-600 px-4 py-2.5 text-sm text-slate-300 transition hover:border-slate-500"
          >
            Anuluj
          </button>
        </div>
      </div>
    </ModalShell>
  );
}

function ModalShell({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-md rounded-2xl border border-border/60 bg-slate-950 p-6 shadow-2xl">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-full p-1 text-slate-500 transition hover:text-slate-300"
        >
          <X className="h-4 w-4" />
        </button>
        {children}
      </div>
    </div>
  );
}
