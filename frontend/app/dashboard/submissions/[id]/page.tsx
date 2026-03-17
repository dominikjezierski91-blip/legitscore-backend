"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

type Submission = {
  id: string;
  created_at: string | null;
  status: string;
  type: string;
  message: string;
  email: string | null;
  wants_reply: boolean;
  user_id: string | null;
  auth_state: string | null;
  source_page: string | null;
  current_url: string | null;
  app_section: string | null;
  report_id: string | null;
  analysis_id: string | null;
  shirt_id: string | null;
  collection_item_id: string | null;
  internal_notes: string | null;
  resolved_at: string | null;
};

const STATUS_OPTIONS = [
  { value: "nowe", label: "Nowe" },
  { value: "w_trakcie", label: "W trakcie" },
  { value: "zamkniete", label: "Zamknięte" },
];

const TYPE_LABELS: Record<string, string> = {
  pytanie: "Pytanie do raportu",
  problem: "Zgłoszenie problemu",
  sugestia: "Sugestia",
  inne: "Inne",
};

export default function SubmissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [sub, setSub] = useState<Submission | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [status, setStatus] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!API_BASE_URL || !id) return;
    const apiBase = API_BASE_URL.replace(/\/$/, "");
    fetch(`${apiBase}/api/support/${id}`, { cache: "no-store" })
      .then(async (res) => {
        if (res.status === 404) { setNotFound(true); return; }
        const data = await res.json();
        setSub(data);
        setStatus(data.status);
        setNotes(data.internal_notes ?? "");
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleSave() {
    if (!API_BASE_URL || !id) return;
    setSaving(true);
    setSaved(false);
    try {
      const apiBase = API_BASE_URL.replace(/\/$/, "");
      const res = await fetch(`${apiBase}/api/support/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, internal_notes: notes }),
      });
      if (res.ok) {
        const updated = await res.json();
        setSub(updated);
        setSaved(true);
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="min-h-screen bg-slate-950 p-8 text-slate-400">Ładowanie...</div>;
  }
  if (notFound || !sub) {
    return <div className="min-h-screen bg-slate-950 p-8 text-red-300">Zgłoszenie nie istnieje.</div>;
  }

  return (
    <div className="min-h-screen bg-slate-950 p-6 text-slate-100">
      <div className="mx-auto max-w-3xl space-y-6">
        <div>
          <a href="/dashboard/submissions" className="text-xs text-slate-500 hover:text-slate-300">
            ← Zgłoszenia
          </a>
          <h1 className="mt-1 text-xl font-bold">Szczegóły zgłoszenia</h1>
        </div>

        {/* Main card */}
        <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-5 space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <TypeBadge type={sub.type} />
            <StatusBadge status={sub.status} />
            <span className="text-xs text-slate-500">{sub.created_at ? formatDate(sub.created_at) : "—"}</span>
          </div>

          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mb-1">Wiadomość</p>
            <p className="text-sm text-slate-100 whitespace-pre-wrap leading-relaxed">{sub.message}</p>
          </div>
        </div>

        {/* Metadata */}
        <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mb-3">Dane zgłaszającego</p>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
            <Row label="Email" value={sub.email} />
            <Row label="Chce odpowiedź" value={sub.wants_reply ? "Tak" : "Nie"} />
            <Row label="User ID" value={sub.user_id} mono />
            <Row label="Stan auth" value={sub.auth_state} />
            <Row label="Sekcja aplikacji" value={sub.app_section} />
            <Row label="Strona źródłowa" value={sub.source_page} />
            <Row label="Report ID" value={sub.report_id} mono />
            <Row label="Analysis ID" value={sub.analysis_id} mono />
            <Row label="Shirt ID" value={sub.shirt_id} mono />
            <Row label="Zamknięte o" value={sub.resolved_at ? formatDate(sub.resolved_at) : null} />
          </dl>
          {sub.current_url && (
            <div className="mt-3">
              <p className="text-[11px] text-slate-500">URL</p>
              <p className="mt-0.5 break-all font-mono text-[11px] text-slate-400">{sub.current_url}</p>
            </div>
          )}
        </div>

        {/* Status + notes edit */}
        <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-5 space-y-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Zarządzanie zgłoszeniem</p>

          <div className="space-y-1">
            <label className="text-xs text-slate-400">Status</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full rounded-lg border border-slate-600/60 bg-slate-800/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-emerald-500/40"
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs text-slate-400">Notatki wewnętrzne</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={4}
              placeholder="Opcjonalne notatki widoczne tylko w backoffice..."
              className="w-full resize-none rounded-lg border border-slate-600/60 bg-slate-800/60 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-emerald-500/40"
            />
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded-full bg-emerald-500 px-5 py-2 text-sm font-medium text-slate-950 transition hover:bg-emerald-400 disabled:opacity-60"
            >
              {saving ? "Zapisywanie..." : "Zapisz zmiany"}
            </button>
            {saved && <span className="text-xs text-emerald-400">Zapisano.</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string | null | undefined; mono?: boolean }) {
  return (
    <>
      <dt className="text-slate-500">{label}</dt>
      <dd className={mono ? "font-mono text-slate-400" : "text-slate-300"}>
        {value ?? <span className="text-slate-600">—</span>}
      </dd>
    </>
  );
}

function TypeBadge({ type }: { type: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    pytanie: { label: "Pytanie", cls: "bg-blue-500/20 text-blue-300 border-blue-400/40" },
    problem: { label: "Problem", cls: "bg-red-500/20 text-red-300 border-red-400/40" },
    sugestia: { label: "Sugestia", cls: "bg-purple-500/20 text-purple-300 border-purple-400/40" },
    inne: { label: "Inne", cls: "bg-slate-500/20 text-slate-300 border-slate-400/40" },
  };
  const m = map[type] ?? { label: type, cls: "bg-slate-700 text-slate-300" };
  return (
    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${m.cls}`}>
      {m.label}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    nowe: { label: "Nowe", cls: "bg-blue-500/20 text-blue-300 border-blue-400/40" },
    w_trakcie: { label: "W trakcie", cls: "bg-amber-500/20 text-amber-300 border-amber-400/40" },
    zamkniete: { label: "Zamknięte", cls: "bg-slate-500/20 text-slate-400 border-slate-500/40" },
  };
  const m = map[status] ?? { label: status, cls: "bg-slate-700 text-slate-300" };
  return (
    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${m.cls}`}>
      {m.label}
    </span>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("pl-PL", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}
