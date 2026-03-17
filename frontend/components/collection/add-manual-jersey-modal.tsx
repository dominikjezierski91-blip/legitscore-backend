"use client";

import { useRef, useState } from "react";
import { X, Upload, Loader2 } from "lucide-react";
import { addToCollection, uploadCollectionPhoto } from "@/lib/api";
import { cn } from "@/lib/utils";

const VERDICT_OPTIONS = [
  { value: "oryginalna_sklepowa", label: "Oryginalna (sklepowa)" },
  { value: "meczowa", label: "Meczowa" },
  { value: "oficjalna_replika", label: "Oficjalna replika" },
  { value: "edycja_limitowana", label: "Edycja limitowana" },
  { value: "treningowa_custom", label: "Treningowa / custom" },
  { value: "podrobka", label: "Podróbka" },
];

const CURRENCY_OPTIONS = ["PLN", "EUR", "GBP", "USD"];

interface Props {
  onClose: () => void;
  onAdded: (item: any) => void;
}

export function AddManualJerseyModal({ onClose, onAdded }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const [form, setForm] = useState({
    club: "",
    season: "",
    brand: "",
    verdict_category: "",
    model_type: "",
    player_name: "",
    player_number: "",
    purchase_price: "",
    purchase_currency: "PLN",
    purchase_date: "",
    purchase_source: "",
    notes: "",
  });

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

  function validate() {
    const e: Record<string, string> = {};
    if (!form.club.trim()) e.club = "Wymagane";
    if (!form.season.trim()) e.season = "Wymagane";
    if (!form.brand.trim()) e.brand = "Wymagane";
    if (!form.verdict_category) e.verdict_category = "Wymagane";
    if (!photoFile) e.photo = "Zdjęcie jest wymagane";
    return e;
  }

  async function handleSubmit() {
    const e = validate();
    if (Object.keys(e).length > 0) { setErrors(e); return; }

    setSaving(true);
    try {
      const item: any = await addToCollection({
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

      if (photoFile) {
        await uploadCollectionPhoto(item.id, photoFile);
        item.has_photo = true;
      }

      onAdded(item);
    } catch (err: any) {
      setErrors({ submit: err.message || "Nie udało się dodać koszulki." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 sm:items-center" onClick={onClose}>
      <div
        className="glass-card w-full max-w-md max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-slate-100">Dodaj koszulkę ręcznie</h2>
          <button onClick={onClose} className="rounded-full p-1 text-slate-500 hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Zdjęcie */}
        <div>
          <label className="block text-[11px] text-slate-400 mb-1.5">
            Zdjęcie profilowe <span className="text-red-400">*</span>
          </label>
          <div
            onClick={() => fileRef.current?.click()}
            className={cn(
              "flex h-28 w-full cursor-pointer items-center justify-center rounded-xl border-2 border-dashed transition",
              errors.photo ? "border-red-500/60 bg-red-950/20" : "border-slate-600/60 bg-slate-800/40 hover:border-emerald-500/40"
            )}
          >
            {photoPreview ? (
              <img src={photoPreview} alt="" className="h-full w-full rounded-xl object-cover" />
            ) : (
              <div className="flex flex-col items-center gap-1 text-slate-500">
                <Upload className="h-5 w-5" />
                <span className="text-[11px]">Kliknij aby wybrać zdjęcie</span>
              </div>
            )}
          </div>
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handlePhotoChange} />
          {errors.photo && <p className="mt-1 text-[10px] text-red-400">{errors.photo}</p>}
        </div>

        {/* Wymagane */}
        <p className="text-[10px] text-slate-500 -mb-2">Pola wymagane oznaczone *</p>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Drużyna / Reprezentacja *" error={errors.club}>
            <input className={inputCls(errors.club)} value={form.club} onChange={(e) => set("club", e.target.value)} placeholder="np. FC Barcelona" />
          </Field>
          <Field label="Sezon *" error={errors.season}>
            <input className={inputCls(errors.season)} value={form.season} onChange={(e) => set("season", e.target.value)} placeholder="np. 2023/24" />
          </Field>
          <Field label="Marka *" error={errors.brand}>
            <input className={inputCls(errors.brand)} value={form.brand} onChange={(e) => set("brand", e.target.value)} placeholder="np. Nike" />
          </Field>
          <Field label="Typ koszulki *" error={errors.verdict_category}>
            <select className={inputCls(errors.verdict_category)} value={form.verdict_category} onChange={(e) => set("verdict_category", e.target.value)}>
              <option value="">Wybierz...</option>
              {VERDICT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Model" error={undefined}>
            <input className={inputCls()} value={form.model_type} onChange={(e) => set("model_type", e.target.value)} placeholder="np. domowa" />
          </Field>
          <Field label="Zawodnik" error={undefined}>
            <input className={inputCls()} value={form.player_name} onChange={(e) => set("player_name", e.target.value)} placeholder="np. Lewandowski" />
          </Field>
          <Field label="Numer" error={undefined}>
            <input className={inputCls()} value={form.player_number} onChange={(e) => set("player_number", e.target.value)} placeholder="np. 9" />
          </Field>
          <Field label="Cena zakupu" error={undefined}>
            <div className="flex gap-1">
              <input className={cn(inputCls(), "flex-1 min-w-0")} value={form.purchase_price} onChange={(e) => set("purchase_price", e.target.value)} placeholder="350" />
              <select className={cn(inputCls(), "w-16 shrink-0")} value={form.purchase_currency} onChange={(e) => set("purchase_currency", e.target.value)}>
                {CURRENCY_OPTIONS.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
          </Field>
          <Field label="Data zakupu" error={undefined}>
            <input type="date" className={inputCls()} value={form.purchase_date} onChange={(e) => set("purchase_date", e.target.value)} />
          </Field>
          <Field label="Źródło zakupu" error={undefined}>
            <input className={inputCls()} value={form.purchase_source} onChange={(e) => set("purchase_source", e.target.value)} placeholder="np. Vinted" />
          </Field>
        </div>

        <Field label="Notatki" error={undefined}>
          <textarea className={cn(inputCls(), "resize-none h-16")} value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Opcjonalne uwagi..." />
        </Field>

        {errors.submit && <p className="text-[11px] text-red-400">{errors.submit}</p>}

        <button
          onClick={handleSubmit}
          disabled={saving}
          className="w-full rounded-full bg-emerald-500 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {saving ? "Dodawanie..." : "Dodaj do kolekcji"}
        </button>
      </div>
    </div>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label className="text-[11px] text-slate-400 truncate">{label}</label>
      {children}
      {error && <p className="text-[10px] text-red-400">{error}</p>}
    </div>
  );
}

function inputCls(error?: string) {
  return cn(
    "w-full rounded-lg border bg-slate-900/60 px-2.5 py-1.5 text-[12px] text-slate-100 outline-none transition",
    error ? "border-red-500/60 focus:border-red-400" : "border-slate-600/50 focus:border-emerald-500/60"
  );
}
