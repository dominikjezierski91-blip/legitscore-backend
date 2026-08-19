"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { X, Upload, Loader2, CheckCircle2 } from "lucide-react";
import { addToCollection, updateCollectionItem, uploadCollectionPhoto, getCollectionThumbnailUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

export const VERDICT_OPTIONS = [
  { value: "oryginalna_sklepowa", label: "Oryginalna (sklepowa)" },
  { value: "meczowa", label: "Meczowa" },
  { value: "oficjalna_replika", label: "Oficjalna replika" },
  { value: "edycja_limitowana", label: "Edycja limitowana" },
  { value: "treningowa_custom", label: "Treningowa / custom" },
  { value: "podrobka", label: "Podróbka" },
];

const CURRENCY_OPTIONS = ["PLN", "EUR", "GBP", "USD"];

// Wartości uznawane za "niezweryfikowane" — pole można edytować
const UNKNOWN_VALUES = new Set(["nieustalone", "unknown", "brak", "—", "n/a", "", "nie dotyczy", "niezweryfikowane"]);
function isUnknown(v: any) {
  return v == null || UNKNOWN_VALUES.has(String(v).toLowerCase().trim());
}

// Pola uzupełniane przez model — zablokowane w edycji, jeśli mają realną wartość
const MODEL_FIELDS = ["club", "season", "brand", "model_type", "player_name", "player_number", "verdict_category"] as const;

const FIELD_MAX_LENGTHS: Record<string, number> = {
  club: 80,
  player_name: 60,
  brand: 40,
  model_type: 40,
  season: 20,
  purchase_source: 60,
  notes: 500,
};

function apiBase() {
  return (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");
}

// Istniejące zdjęcie danej pozycji (slot 1/2) — do podglądu w trybie edycji.
function existingPhotoSrc(item: any, slot: 1 | 2): string | null {
  if (!item) return null;
  if (item.has_photo) {
    if (slot === 2) return item.has_photo_2 ? getCollectionThumbnailUrl(item.id, 2) : null;
    return getCollectionThumbnailUrl(item.id, 1);
  }
  if (item.case_id && !item.is_manual) {
    return `${apiBase()}/api/cases/${item.case_id}/thumbnail?index=${slot - 1}`;
  }
  return null;
}

interface Props {
  mode: "add" | "edit";
  item?: any; // wymagane przy mode === "edit"
  onClose: () => void;
  onSaved: (item: any) => void;
}

export function JerseyFormModal({ mode, item, onClose, onSaved }: Props) {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const fileRef2 = useRef<HTMLInputElement>(null);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(
    mode === "edit" ? existingPhotoSrc(item, 1) : null
  );
  const [photoFile2, setPhotoFile2] = useState<File | null>(null);
  const [photoPreview2, setPhotoPreview2] = useState<string | null>(
    mode === "edit" ? existingPhotoSrc(item, 2) : null
  );
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [success, setSuccess] = useState(false);

  const [form, setForm] = useState({
    club: item?.club || "",
    season: item?.season || "",
    brand: item?.brand || "",
    verdict_category: item?.verdict_category || "",
    model_type: item?.model_type || "",
    player_name: item?.player_name || "",
    player_number: item?.player_number || "",
    purchase_price: item?.purchase_price || "",
    purchase_currency: item?.purchase_currency || "PLN",
    purchase_date: item?.purchase_date || "",
    purchase_source: item?.purchase_source || "",
    notes: item?.notes || "",
  });

  // Pole zablokowane: wypełnione przez model i nie-unknown — tylko w edycji
  // przeanalizowanej (nie ręcznej) koszulki. W trybie dodawania nic nie jest
  // zablokowane — to zawsze świeży, ręczny wpis.
  function isLocked(field: string): boolean {
    if (mode !== "edit" || !item || item.is_manual) return false;
    if (!(MODEL_FIELDS as readonly string[]).includes(field)) return false;
    return !isUnknown(item[field]);
  }

  function set(field: string, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
    setErrors((e) => { const n = { ...e }; delete n[field]; return n; });
  }

  function handlePhotoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhotoFile(file);
    setPhotoPreview(URL.createObjectURL(file));
    setErrors((e) => { const n = { ...e }; delete n.photo; return n; });
  }

  function handlePhotoChange2(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhotoFile2(file);
    setPhotoPreview2(URL.createObjectURL(file));
  }

  function validate() {
    const e: Record<string, string> = {};
    // Wymagane pola tylko dla ręcznych wpisów (nowych albo edytowanych) —
    // przeanalizowana koszulka z niepotwierdzonymi (nieustalone) polami nie
    // musi być uzupełniona, żeby zapisać inne zmiany.
    const requireCore = mode === "add" || Boolean(item?.is_manual);
    if (requireCore) {
      if (!form.club.trim()) e.club = "Wymagane";
      if (!form.season.trim()) e.season = "Wymagane";
      if (!form.brand.trim()) e.brand = "Wymagane";
      if (!form.verdict_category) e.verdict_category = "Wymagane";
    }
    if (mode === "add" && !photoFile) e.photo = "Zdjęcie jest wymagane";
    for (const [field, maxLen] of Object.entries(FIELD_MAX_LENGTHS)) {
      const val = form[field as keyof typeof form];
      if (val && String(val).length > maxLen) {
        e[field] = `Maksymalnie ${maxLen} znaków`;
      }
    }
    return e;
  }

  async function handleSubmit() {
    const e = validate();
    if (Object.keys(e).length > 0) { setErrors(e); return; }

    setSaving(true);
    try {
      let saved: any;
      if (mode === "add") {
        saved = await addToCollection({
          case_id: undefined as any,
          is_manual: true,
          club: form.club.trim(),
          season: form.season.trim(),
          brand: form.brand.trim(),
          verdict_category: form.verdict_category,
          model_type: form.model_type.trim() || undefined,
          player_name: form.player_name.trim() || undefined,
          player_number: form.player_number.trim() || undefined,
          purchase_price: form.purchase_price.trim() || undefined,
          purchase_currency: form.purchase_currency || undefined,
          purchase_date: form.purchase_date || undefined,
          purchase_source: form.purchase_source.trim() || undefined,
          notes: form.notes.trim() || undefined,
        });
      } else {
        saved = await updateCollectionItem(item.id, {
          club: form.club.trim() || undefined,
          season: form.season.trim() || undefined,
          brand: form.brand.trim() || undefined,
          model_type: form.model_type.trim() || undefined,
          player_name: form.player_name.trim() || undefined,
          player_number: form.player_number.trim() || undefined,
          verdict_category: form.verdict_category || undefined,
          purchase_price: form.purchase_price.trim() || undefined,
          purchase_currency: form.purchase_currency || undefined,
          purchase_date: form.purchase_date || undefined,
          purchase_source: form.purchase_source.trim() || undefined,
          notes: form.notes.trim() || undefined,
        });
      }

      if (photoFile) {
        await uploadCollectionPhoto(saved.id, photoFile, 1);
        saved.has_photo = true;
      }
      if (photoFile2) {
        await uploadCollectionPhoto(saved.id, photoFile2, 2);
        saved.has_photo_2 = true;
      }

      if (mode === "add") {
        onSaved(saved);
        setSuccess(true);
      } else {
        onSaved(saved);
        onClose();
      }
    } catch (err: any) {
      setErrors({ submit: err.message || "Nie udało się zapisać." });
    } finally {
      setSaving(false);
    }
  }

  if (success) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
        <div className="relative w-full max-w-md rounded-2xl border border-border/60 bg-slate-950 p-6 shadow-2xl space-y-4 text-center" onClick={(e) => e.stopPropagation()}>
          <button onClick={onClose} className="absolute right-4 top-4 rounded-full p-1 text-slate-500 transition hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
          <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-400" />
          <div>
            <h2 className="text-lg font-semibold text-slate-50">Zapisano do kolekcji</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Koszulka została dodana do Twojej kolekcji.
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => router.push("/collection")}
              className="w-full rounded-full bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400"
            >
              Zobacz kolekcję →
            </button>
            <button
              onClick={() => router.push("/analyze")}
              className="w-full rounded-full border border-emerald-400/60 bg-emerald-500/10 px-4 py-2.5 text-sm font-medium text-emerald-200 transition hover:bg-emerald-500/20"
            >
              Nowa analiza
            </button>
          </div>
          <button onClick={onClose} className="text-xs text-muted-foreground hover:text-slate-300 underline underline-offset-2">
            Wróć do kolekcji
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8"
      onClick={onClose}
    >
      <div
        className="glass-card w-full max-w-md space-y-4 rounded-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-100">
            {mode === "add" ? "Dodaj koszulkę ręcznie" : "Edytuj koszulkę"}
          </h2>
          <button onClick={onClose} className="rounded-full p-1 text-slate-500 hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Zdjęcia */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="jersey-photo-1" className="block text-xs text-slate-400 mb-1.5">
              Zdjęcie profilowe {mode === "add" && <span className="text-red-400">*</span>}
            </label>
            <label
              htmlFor="jersey-photo-1"
              className={cn(
                "flex h-28 w-full cursor-pointer items-center justify-center rounded-xl border-2 border-dashed transition",
                errors.photo ? "border-red-500/60 bg-red-950/20" : "border-slate-600/60 bg-slate-800/40 hover:border-emerald-500/40"
              )}
            >
              {photoPreview ? (
                <img src={photoPreview} alt="" className="h-full w-full rounded-xl object-cover" />
              ) : (
                <div className="flex flex-col items-center gap-1 text-slate-500 px-2 text-center">
                  <Upload className="h-5 w-5" />
                  <span className="text-xs">Kliknij aby wybrać zdjęcie</span>
                </div>
              )}
            </label>
            <input id="jersey-photo-1" ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handlePhotoChange} />
            {errors.photo && <p className="mt-1 text-[11px] text-red-400">{errors.photo}</p>}
          </div>

          <div>
            <label htmlFor="jersey-photo-2" className="block truncate text-xs text-slate-400 mb-1.5">
              Drugie zdjęcie
            </label>
            <label
              htmlFor="jersey-photo-2"
              className="flex h-28 w-full cursor-pointer items-center justify-center rounded-xl border-2 border-dashed border-slate-600/60 bg-slate-800/40 transition hover:border-emerald-500/40"
            >
              {photoPreview2 ? (
                <img src={photoPreview2} alt="" className="h-full w-full rounded-xl object-cover" />
              ) : (
                <div className="flex flex-col items-center gap-1 text-slate-500 px-2 text-center">
                  <Upload className="h-5 w-5" />
                  <span className="text-xs">np. tył koszulki</span>
                </div>
              )}
            </label>
            <input id="jersey-photo-2" ref={fileRef2} type="file" accept="image/*" className="hidden" onChange={handlePhotoChange2} />
          </div>
        </div>

        {/* Wymagane */}
        <p className="text-[11px] text-slate-500 -mb-2">Pola wymagane oznaczone *</p>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Drużyna / Reprezentacja *" error={errors.club} disabled={isLocked("club")}>
            <input className={inputCls(errors.club, isLocked("club"))} value={form.club} onChange={(e) => set("club", e.target.value)} placeholder="np. FC Barcelona" disabled={isLocked("club")} />
          </Field>
          <Field label="Sezon *" error={errors.season} disabled={isLocked("season")}>
            <input className={inputCls(errors.season, isLocked("season"))} value={form.season} onChange={(e) => set("season", e.target.value)} placeholder="np. 2023/24" disabled={isLocked("season")} />
          </Field>
          <Field label="Marka *" error={errors.brand} disabled={isLocked("brand")}>
            <input className={inputCls(errors.brand, isLocked("brand"))} value={form.brand} onChange={(e) => set("brand", e.target.value)} placeholder="np. Nike" disabled={isLocked("brand")} />
          </Field>
          <Field label="Typ koszulki *" error={errors.verdict_category} disabled={isLocked("verdict_category")}>
            <select className={inputCls(errors.verdict_category, isLocked("verdict_category"))} value={form.verdict_category} onChange={(e) => set("verdict_category", e.target.value)} disabled={isLocked("verdict_category")}>
              <option value="">Wybierz...</option>
              {VERDICT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Model" disabled={isLocked("model_type")}>
            <input className={inputCls(undefined, isLocked("model_type"))} value={form.model_type} onChange={(e) => set("model_type", e.target.value)} placeholder="np. domowa" disabled={isLocked("model_type")} />
          </Field>
          <Field label="Zawodnik" disabled={isLocked("player_name")}>
            <input className={inputCls(undefined, isLocked("player_name"))} value={form.player_name} onChange={(e) => set("player_name", e.target.value)} placeholder="np. Lewandowski" disabled={isLocked("player_name")} />
          </Field>
          <Field label="Numer" disabled={isLocked("player_number")}>
            <input className={inputCls(undefined, isLocked("player_number"))} value={form.player_number} onChange={(e) => set("player_number", e.target.value)} placeholder="np. 9" disabled={isLocked("player_number")} />
          </Field>
          <Field label="Cena zakupu">
            <div className="flex gap-1">
              <input className={cn(inputCls(), "flex-1 min-w-0")} value={form.purchase_price} onChange={(e) => set("purchase_price", e.target.value)} placeholder="350" />
              <select className={cn(inputCls(), "w-16 shrink-0")} value={form.purchase_currency} onChange={(e) => set("purchase_currency", e.target.value)}>
                {CURRENCY_OPTIONS.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
          </Field>
          <Field label="Data zakupu">
            <input type="date" className={inputCls()} value={form.purchase_date} onChange={(e) => set("purchase_date", e.target.value)} />
          </Field>
          <Field label="Źródło zakupu">
            <input className={inputCls()} value={form.purchase_source} onChange={(e) => set("purchase_source", e.target.value)} placeholder="np. Vinted" />
          </Field>
        </div>

        <Field label="Notatki" error={errors.notes}>
          <textarea className={cn(inputCls(errors.notes), "resize-none h-16")} value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Opcjonalne uwagi..." />
        </Field>

        {errors.submit && <p className="text-xs text-red-400">{errors.submit}</p>}

        <button
          onClick={handleSubmit}
          disabled={saving}
          className="w-full rounded-full bg-emerald-500 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {mode === "add" ? (saving ? "Dodawanie..." : "Dodaj do kolekcji") : (saving ? "Zapisywanie..." : "Zapisz")}
        </button>
      </div>
    </div>
  );
}

function Field({ label, error, disabled, children }: { label: string; error?: string; disabled?: boolean; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label className={cn("truncate text-xs", disabled ? "text-slate-600" : "text-slate-400")}>{label}</label>
      {children}
      {error && <p className="text-[11px] text-red-400">{error}</p>}
    </div>
  );
}

function inputCls(error?: string, disabled?: boolean) {
  return cn(
    "w-full rounded-lg border bg-slate-900/60 px-2.5 py-1.5 text-sm text-slate-100 outline-none transition",
    disabled
      ? "border-slate-700/40 text-slate-600 cursor-not-allowed opacity-60"
      : error
      ? "border-red-500/60 focus:border-red-400"
      : "border-slate-600/50 focus:border-emerald-500/60"
  );
}
