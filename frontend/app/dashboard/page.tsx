"use client";

import { useState, useEffect, useCallback } from "react";
import { MonitoringSection } from "./components/monitoring-section";

const API = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "";

// ── Types ──────────────────────────────────────────────────────────────────

type CaseRecord = {
  case_id: string;
  created_at: string | null;
  email: string | null;
  verdict_category: string | null;
  confidence_percent: string | null;
  feedback: string | null;
  feedback_comment: string | null;
  rating: number | null;
  sku: string | null;
  model: string | null;
  prompt_version: string | null;
  auth_state: string | null;
};

type CasesResponse = {
  cases: CaseRecord[];
  total: number;
  page: number;
  limit: number;
};

type Stats = {
  total: number;
  with_feedback: number;
  correct: number;
  incorrect: number;
  unsure: number;
};

type UserStats = {
  total: number;
  new_today: number;
  new_7d: number;
  active_7d: number;
};

type UserRecord = {
  id: string;
  email: string;
  created_at: string | null;
  is_admin: boolean;
  analysis_count: number;
  collection_count: number;
  last_activity_at: string | null;
  user_type: string | null;
};

type Metrics = {
  total_cases: number;
  cases_today: number;
  cases_7d: number;
  logged_in_cases: number;
  guest_cases: number;
  collection_adoption_pct: number;
  avg_analyses_per_user: number;
  activation_rate_pct: number;
  users_with_analysis: number;
  segments?: {
    user_type: Record<string, number>;
    collection_size: Record<string, number>;
    survey_completed: number;
    survey_skipped: number;
  };
};

type ActivationData = {
  avg_hours_to_first_analysis: number | null;
  unactivated_count: number;
  unactivated_users: { id: string; email: string; created_at: string | null }[];
};

type RetentionData = {
  retention_7d_pct: number;
  active_7d_count: number;
  engaged_pct: number;
  engaged_count: number;
  churned_count: number;
  churned_users: { id: string; email: string; last_activity_at: string; created_at: string | null }[];
};

type RegTrend = { date: string; count: number }[];

type UserDetail = {
  id: string;
  email: string;
  created_at: string | null;
  is_admin: boolean;
  user_type: string | null;
  cases: {
    case_id: string;
    created_at: string | null;
    verdict_category: string | null;
    confidence_percent: string | null;
    feedback: string | null;
    sku: string | null;
  }[];
};

// ── Helpers ────────────────────────────────────────────────────────────────

function fmt(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("pl-PL", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("pl-PL", {
      day: "2-digit", month: "2-digit", year: "numeric",
    });
  } catch { return iso; }
}

async function apiFetch<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

// ── Mini components ────────────────────────────────────────────────────────

function Chip({ children, cls }: { children: React.ReactNode; cls: string }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${cls}`}>
      {children}
    </span>
  );
}

function VerdictBadge({ c }: { c: string | null }) {
  if (!c) return <span className="text-slate-600 text-xs">—</span>;
  const map: Record<string, [string, string]> = {
    meczowa: ["Meczowa", "bg-purple-500/20 text-purple-300"],
    oryginalna_sklepowa: ["Oryginalna", "bg-emerald-500/20 text-emerald-300"],
    oficjalna_replika: ["Replika", "bg-blue-500/20 text-blue-300"],
    podrobka: ["Podróbka", "bg-red-500/20 text-red-300"],
    edycja_limitowana: ["Limitowana", "bg-amber-500/20 text-amber-300"],
    treningowa_custom: ["Treningowa", "bg-slate-500/20 text-slate-300"],
  };
  const [label, cls] = map[c] ?? [c, "bg-slate-700 text-slate-300"];
  return <Chip cls={cls}>{label}</Chip>;
}

function FeedbackBadge({ f }: { f: string | null }) {
  if (!f) return <span className="text-slate-600 text-xs">—</span>;
  const map: Record<string, [string, string]> = {
    correct: ["Poprawny", "bg-emerald-500/20 text-emerald-300"],
    incorrect: ["Niepoprawny", "bg-red-500/20 text-red-300"],
    unsure: ["Nie wiem", "bg-amber-500/20 text-amber-300"],
  };
  const [label, cls] = map[f] ?? [f, "bg-slate-700 text-slate-300"];
  return <Chip cls={cls}>{label}</Chip>;
}

function UserStatusBadge({ u }: { u: UserRecord }) {
  if (!u.last_activity_at) return <Chip cls="bg-slate-700 text-slate-400">Nowy</Chip>;
  const daysSince = (Date.now() - new Date(u.last_activity_at).getTime()) / 86400000;
  if (u.analysis_count >= 3) return <Chip cls="bg-emerald-500/20 text-emerald-300">Engaged</Chip>;
  if (daysSince > 14) return <Chip cls="bg-red-500/20 text-red-400">Churned</Chip>;
  return <Chip cls="bg-blue-500/20 text-blue-300">Aktywny</Chip>;
}

function Stat({ label, value, sub, color = "slate" }: { label: string; value: string | number; sub?: string; color?: string }) {
  const border: Record<string, string> = {
    slate: "border-slate-700 bg-slate-800/50",
    emerald: "border-emerald-500/40 bg-emerald-900/20",
    blue: "border-blue-500/40 bg-blue-900/20",
    amber: "border-amber-500/40 bg-amber-900/20",
    red: "border-red-500/40 bg-red-900/20",
    purple: "border-purple-500/40 bg-purple-900/20",
  };
  return (
    <div className={`rounded-xl border p-4 ${border[color] ?? border.slate}`}>
      <div className="text-xl font-bold tabular-nums">{value}</div>
      <div className="text-xs text-slate-400">{label}</div>
      {sub && <div className="mt-0.5 text-[10px] text-slate-600">{sub}</div>}
    </div>
  );
}

function Sparkline({ data }: { data: RegTrend }) {
  if (data.length < 2) return null;
  const vals = data.map((d) => d.count);
  const max = Math.max(...vals, 1);
  const W = 200, H = 40;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * W;
    const y = H - (v / max) * H;
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg width={W} height={H} className="overflow-visible">
      <polyline
        points={pts}
        fill="none"
        stroke="rgb(52 211 153)"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function Loading() {
  return <div className="py-12 text-center text-sm text-slate-500">Ładowanie…</div>;
}

// ── Tab: Przegląd ──────────────────────────────────────────────────────────

function TabOverview() {
  const [userStats, setUserStats] = useState<UserStats | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [activation, setActivation] = useState<ActivationData | null>(null);
  const [retention, setRetention] = useState<RetentionData | null>(null);
  const [trend, setTrend] = useState<RegTrend>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      apiFetch<UserStats>("/api/dashboard/user-stats"),
      apiFetch<Metrics>("/api/dashboard/metrics"),
      apiFetch<ActivationData>("/api/dashboard/activation"),
      apiFetch<RetentionData>("/api/dashboard/retention"),
      apiFetch<RegTrend>("/api/dashboard/registrations"),
    ]).then(([us, m, a, r, t]) => {
      setUserStats(us);
      setMetrics(m);
      setActivation(a);
      setRetention(r);
      setTrend(t);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <Loading />;
  if (!userStats || !metrics) return <div className="py-8 text-center text-slate-500">Brak danych</div>;

  const trendMax = trend.reduce((a, b) => Math.max(a, b.count), 0);

  return (
    <div className="space-y-8">

      {/* Acquisition */}
      <section className="space-y-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">Akwizycja</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Zarejestrowani łącznie" value={userStats.total} color="slate" />
          <Stat label="Nowi dziś" value={userStats.new_today} color="emerald" />
          <Stat label="Nowi 7 dni" value={userStats.new_7d} color="blue" />
          <Stat label="Aktywni 7 dni" value={userStats.active_7d} color="amber" />
        </div>
        {trend.length > 1 && (
          <div className="rounded-xl border border-slate-700/60 bg-slate-900/40 p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] text-slate-500">Rejestracje — ostatnie 30 dni</span>
              <span className="text-[11px] text-slate-400">max {trendMax}/dzień</span>
            </div>
            <Sparkline data={trend} />
            <div className="mt-1 flex justify-between text-[10px] text-slate-600">
              <span>{fmtDate(trend[0].date)}</span>
              <span>{fmtDate(trend[trend.length - 1].date)}</span>
            </div>
          </div>
        )}
      </section>

      {/* Activation */}
      <section className="space-y-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">Aktywacja</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Stat
            label="Wskaźnik aktywacji"
            value={`${metrics.activation_rate_pct}%`}
            sub={`${metrics.users_with_analysis} z ${userStats.total} użytkowników`}
            color="emerald"
          />
          <Stat
            label="Śr. czas do 1. analizy"
            value={activation?.avg_hours_to_first_analysis != null
              ? `${activation.avg_hours_to_first_analysis}h`
              : "—"}
            sub="od rejestracji"
            color="blue"
          />
          <Stat
            label="Nieaktywowani"
            value={activation?.unactivated_count ?? "—"}
            sub="bez żadnej analizy"
            color="red"
          />
        </div>
        {activation && activation.unactivated_users.length > 0 && (
          <div className="rounded-xl border border-slate-700/60 bg-slate-900/40 p-4">
            <p className="mb-2 text-[11px] text-slate-500">Nieaktywowani użytkownicy (ostatnie {activation.unactivated_users.length})</p>
            <div className="space-y-1">
              {activation.unactivated_users.slice(0, 10).map((u) => (
                <div key={u.id} className="flex justify-between text-xs">
                  <span className="text-slate-300">{u.email}</span>
                  <span className="text-slate-600">{fmtDate(u.created_at)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Retention */}
      <section className="space-y-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">Retencja</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat
            label="Retencja 7-dniowa"
            value={retention ? `${retention.retention_7d_pct}%` : "—"}
            sub={`${retention?.active_7d_count ?? 0} aktywnych w tygodniu`}
            color="emerald"
          />
          <Stat
            label="Engaged (≥3 analizy)"
            value={retention ? `${retention.engaged_pct}%` : "—"}
            sub={`${retention?.engaged_count ?? 0} użytkowników`}
            color="purple"
          />
          <Stat
            label="Churned (>14 dni braku)"
            value={retention?.churned_count ?? "—"}
            sub="użytkowników"
            color="red"
          />
          <Stat
            label="Kolekcja adoption"
            value={`${metrics.collection_adoption_pct}%`}
            sub="z aktywnych użytkowników"
            color="blue"
          />
        </div>
        {retention && retention.churned_users.length > 0 && (
          <div className="rounded-xl border border-slate-700/60 bg-slate-900/40 p-4">
            <p className="mb-2 text-[11px] text-slate-500">Churned — ostatnia aktywność</p>
            <div className="space-y-1">
              {retention.churned_users.slice(0, 8).map((u) => (
                <div key={u.id} className="flex justify-between text-xs">
                  <span className="text-slate-300">{u.email}</span>
                  <span className="text-red-400/70">{fmtDate(u.last_activity_at)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Engagement */}
      <section className="space-y-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">Zaangażowanie</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Stat label="Analiz łącznie" value={metrics.total_cases} color="slate" />
          <Stat label="Analiz dziś" value={metrics.cases_today} color="emerald" />
          <Stat
            label="Śr. analiz / użytkownik"
            value={metrics.avg_analyses_per_user}
            sub="na aktywnych"
            color="blue"
          />
        </div>
        {metrics.segments && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-700/60 bg-slate-900/40 p-4 space-y-2">
              <p className="text-[11px] font-semibold text-slate-500">Typ użytkownika</p>
              {Object.entries(metrics.segments.user_type).map(([k, v]) => (
                <SegBar key={k} label={k} value={v} total={metrics.segments!.survey_completed} />
              ))}
              <p className="text-[10px] text-slate-600 pt-1">
                Ankieta: {metrics.segments.survey_completed} · pominęli: {metrics.segments.survey_skipped}
              </p>
            </div>
            <div className="rounded-xl border border-slate-700/60 bg-slate-900/40 p-4 space-y-2">
              <p className="text-[11px] font-semibold text-slate-500">Rozmiar kolekcji</p>
              {Object.entries(metrics.segments.collection_size).map(([k, v]) => (
                <SegBar key={k} label={k} value={v} total={metrics.segments!.survey_completed} />
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function SegBar({ label, value, total }: { label: string; value: number; total: number }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="w-28 shrink-0 text-xs text-slate-400 truncate">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-slate-800">
        <div className="h-1.5 rounded-full bg-emerald-500/60" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-6 text-right text-[11px] text-slate-500">{value}</span>
    </div>
  );
}

// ── Tab: Raporty ───────────────────────────────────────────────────────────

function TabReports() {
  const [data, setData] = useState<CasesResponse | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [page, setPage] = useState(1);
  const [emailFilter, setEmailFilter] = useState("");
  const [emailInput, setEmailInput] = useState("");
  const [verdictFilter, setVerdictFilter] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback((p: number, email: string, verdict: string) => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(p), limit: "25" });
    if (email) params.set("email", email);
    if (verdict) params.set("verdict", verdict);
    Promise.all([
      apiFetch<CasesResponse>(`/api/dashboard/cases?${params}`),
      apiFetch<Stats>("/api/dashboard/stats"),
    ]).then(([c, s]) => {
      setData(c);
      setStats(s);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(1, "", ""); }, [load]);

  function applyFilter() {
    setPage(1);
    setEmailFilter(emailInput);
    load(1, emailInput, verdictFilter);
  }

  function clearFilter() {
    setEmailInput("");
    setEmailFilter("");
    setVerdictFilter("");
    setPage(1);
    load(1, "", "");
  }

  function goPage(p: number) {
    setPage(p);
    load(p, emailFilter, verdictFilter);
  }

  const totalPages = data ? Math.ceil(data.total / 25) : 1;

  return (
    <div className="space-y-4">
      {stats && (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          <Stat label="Wszystkie" value={stats.total} color="slate" />
          <Stat label="Z feedbackiem" value={stats.with_feedback} color="blue" />
          <Stat label="Poprawne" value={stats.correct} color="emerald" />
          <Stat label="Niepoprawne" value={stats.incorrect} color="red" />
          <Stat label="Nie wiem" value={stats.unsure} color="amber" />
        </div>
      )}

      {/* Filter bar */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-700/60 bg-slate-900/40 p-3">
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-slate-500">Email</label>
          <input
            value={emailInput}
            onChange={(e) => setEmailInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyFilter()}
            placeholder="Filtruj po emailu…"
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:border-emerald-500/50 focus:outline-none w-52"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-slate-500">Werdykt</label>
          <select
            value={verdictFilter}
            onChange={(e) => { setVerdictFilter(e.target.value); }}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:border-emerald-500/50 focus:outline-none"
          >
            <option value="">Wszystkie</option>
            <option value="meczowa">Meczowa</option>
            <option value="oryginalna_sklepowa">Oryginalna</option>
            <option value="oficjalna_replika">Replika</option>
            <option value="podrobka">Podróbka</option>
            <option value="edycja_limitowana">Limitowana</option>
            <option value="treningowa_custom">Treningowa</option>
          </select>
        </div>
        <button
          onClick={applyFilter}
          className="rounded-lg bg-emerald-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600"
        >
          Szukaj
        </button>
        {(emailFilter || verdictFilter) && (
          <button
            onClick={clearFilter}
            className="rounded-lg border border-slate-600 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200"
          >
            Wyczyść
          </button>
        )}
        {data && (
          <span className="ml-auto text-xs text-slate-500">
            {data.total} wyników · strona {page}/{totalPages}
          </span>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-700 bg-slate-900/50">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-700 bg-slate-800/50 text-xs uppercase text-slate-400">
            <tr>
              <th className="px-3 py-2.5">Data</th>
              <th className="px-3 py-2.5">Case ID</th>
              <th className="px-3 py-2.5">Email</th>
              <th className="px-3 py-2.5">SKU</th>
              <th className="px-3 py-2.5">Model</th>
              <th className="px-3 py-2.5">Werdykt</th>
              <th className="px-3 py-2.5">Pewność</th>
              <th className="px-3 py-2.5">Feedback</th>
              <th className="px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {loading ? (
              <tr><td colSpan={9} className="py-8 text-center text-slate-500">Ładowanie…</td></tr>
            ) : !data || data.cases.length === 0 ? (
              <tr><td colSpan={9} className="py-8 text-center text-slate-500">Brak wyników</td></tr>
            ) : data.cases.map((c) => (
              <tr key={c.case_id} className="hover:bg-slate-800/30">
                <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-400">{fmt(c.created_at)}</td>
                <td className="px-3 py-2 font-mono text-xs text-slate-500">{c.case_id.slice(0, 8)}…</td>
                <td className="px-3 py-2 text-xs text-slate-200">{c.email || <span className="text-slate-600">gość</span>}</td>
                <td className="px-3 py-2 font-mono text-xs text-emerald-300">{c.sku || <span className="text-slate-600">—</span>}</td>
                <td className="px-3 py-2 text-xs text-slate-400">{c.model?.replace("models/", "") || "—"}</td>
                <td className="px-3 py-2"><VerdictBadge c={c.verdict_category} /></td>
                <td className="px-3 py-2 text-xs">{c.confidence_percent ? `${c.confidence_percent}%` : "—"}</td>
                <td className="px-3 py-2"><FeedbackBadge f={c.feedback} /></td>
                <td className="px-3 py-2">
                  <a href={`/case/${c.case_id}`} className="text-xs text-emerald-400 hover:underline">
                    Zobacz
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-1">
          <button
            disabled={page === 1}
            onClick={() => goPage(page - 1)}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-400 disabled:opacity-30 hover:border-slate-500"
          >
            ← Poprzednia
          </button>
          <span className="px-3 text-xs text-slate-500">{page} / {totalPages}</span>
          <button
            disabled={page === totalPages}
            onClick={() => goPage(page + 1)}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-400 disabled:opacity-30 hover:border-slate-500"
          >
            Następna →
          </button>
        </div>
      )}
    </div>
  );
}

// ── Tab: Użytkownicy ───────────────────────────────────────────────────────

function TabUsers() {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [selected, setSelected] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    apiFetch<UserRecord[]>("/api/dashboard/users")
      .then(setUsers)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function openUser(id: string) {
    setDetailLoading(true);
    apiFetch<UserDetail>(`/api/dashboard/users/${id}`)
      .then(setSelected)
      .catch(() => {})
      .finally(() => setDetailLoading(false));
  }

  if (loading) return <Loading />;

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-xl border border-slate-700 bg-slate-900/50">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-700 bg-slate-800/50 text-xs uppercase text-slate-400">
            <tr>
              <th className="px-3 py-2.5">Email</th>
              <th className="px-3 py-2.5">Rejestracja</th>
              <th className="px-3 py-2.5">Status</th>
              <th className="px-3 py-2.5">Analizy</th>
              <th className="px-3 py-2.5">Kolekcja</th>
              <th className="px-3 py-2.5">Ostatnia aktywność</th>
              <th className="px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {users.length === 0 ? (
              <tr><td colSpan={7} className="py-8 text-center text-slate-500">Brak użytkowników</td></tr>
            ) : users.map((u) => (
              <tr key={u.id} className="hover:bg-slate-800/30">
                <td className="px-3 py-2 text-xs text-slate-200">
                  {u.email}
                  {u.is_admin && <Chip cls="ml-2 bg-amber-500/20 text-amber-300">admin</Chip>}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-400">{fmtDate(u.created_at)}</td>
                <td className="px-3 py-2"><UserStatusBadge u={u} /></td>
                <td className="px-3 py-2 text-xs">
                  {u.analysis_count > 0
                    ? <span className="text-emerald-300">{u.analysis_count}</span>
                    : <span className="text-slate-600">0</span>}
                </td>
                <td className="px-3 py-2 text-xs">
                  {u.collection_count > 0
                    ? <span className="text-blue-300">{u.collection_count}</span>
                    : <span className="text-slate-600">0</span>}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-400">{fmtDate(u.last_activity_at)}</td>
                <td className="px-3 py-2">
                  <button
                    onClick={() => openUser(u.id)}
                    className="text-xs text-emerald-400 hover:underline"
                  >
                    Szczegóły
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* User detail modal */}
      {(selected || detailLoading) && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 px-4 py-12 overflow-y-auto"
          onClick={() => setSelected(null)}
        >
          <div
            className="w-full max-w-xl rounded-2xl border border-slate-700 bg-slate-900 p-6 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            {detailLoading && <Loading />}
            {selected && (
              <>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-semibold text-slate-100">{selected.email}</p>
                    <p className="text-xs text-slate-500">Zarejestrowany: {fmt(selected.created_at)}</p>
                  </div>
                  <button
                    onClick={() => setSelected(null)}
                    className="text-slate-500 hover:text-slate-300 text-lg leading-none"
                  >
                    ×
                  </button>
                </div>
                <div className="space-y-1">
                  <p className="text-[11px] text-slate-500">{selected.cases.length} analiz</p>
                  <div className="rounded-lg border border-slate-700 divide-y divide-slate-800 max-h-80 overflow-y-auto">
                    {selected.cases.length === 0 ? (
                      <p className="px-3 py-3 text-xs text-slate-500">Brak analiz</p>
                    ) : selected.cases.map((c) => (
                      <div key={c.case_id} className="flex items-center justify-between px-3 py-2">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-slate-500">{c.case_id.slice(0, 8)}</span>
                          <VerdictBadge c={c.verdict_category} />
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-slate-500">{fmtDate(c.created_at)}</span>
                          <a href={`/case/${c.case_id}`} className="text-xs text-emerald-400 hover:underline">
                            →
                          </a>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tab: Zgłoszenia ────────────────────────────────────────────────────────

function TabSubmissions() {
  return (
    <div className="py-4">
      <iframe
        src="/dashboard/submissions"
        className="w-full rounded-xl border border-slate-700"
        style={{ height: "70vh" }}
        title="Zgłoszenia"
      />
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────

const TABS = [
  { id: "overview", label: "Przegląd" },
  { id: "reports", label: "Raporty" },
  { id: "users", label: "Użytkownicy" },
  { id: "monitoring", label: "Monitoring" },
  { id: "submissions", label: "Zgłoszenia" },
] as const;

type TabId = typeof TABS[number]["id"];

export default function DashboardPage() {
  const [tab, setTab] = useState<TabId>("overview");

  // Support #monitoring hash from nav bug icon
  useEffect(() => {
    if (window.location.hash === "#monitoring") setTab("monitoring");
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-6xl px-4 py-6">

        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-xl font-bold">LegitScore · Dashboard</h1>
        </div>

        {/* Tab bar */}
        <div className="mb-6 flex gap-1 rounded-xl border border-slate-800 bg-slate-900/60 p-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex-1 rounded-lg py-2 text-xs font-medium transition ${
                tab === t.id
                  ? "bg-slate-700 text-slate-100 shadow"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div>
          {tab === "overview" && <TabOverview />}
          {tab === "reports" && <TabReports />}
          {tab === "users" && <TabUsers />}
          {tab === "monitoring" && <MonitoringSection />}
          {tab === "submissions" && <TabSubmissions />}
        </div>

      </div>
    </div>
  );
}
