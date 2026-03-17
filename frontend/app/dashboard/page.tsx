export const dynamic = "force-dynamic";

import { Suspense } from "react";
import { DashboardFilters } from "./components/filters-client";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

type CaseRecord = {
  case_id: string;
  created_at: string | null;
  email: string | null;
  consent_at: string | null;
  offer_link: string | null;
  context: string | null;
  model: string | null;
  prompt_version: string | null;
  verdict_category: string | null;
  confidence_percent: string | null;
  feedback: string | null;
  feedback_at: string | null;
  feedback_comment: string | null;
  rating: number | null;
  rating_at: string | null;
  sku: string | null;
  auth_state: string | null;
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
  collection_size_range: string | null;
  profile_survey_completed_at: string | null;
  profile_survey_skipped_at: string | null;
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

type SearchParams = {
  date_from?: string;
  date_to?: string;
  auth_state?: string;
  verdict?: string;
};

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  if (!API_BASE_URL) {
    return (
      <div className="p-8 text-amber-200">
        Brak konfiguracji NEXT_PUBLIC_API_BASE_URL.
      </div>
    );
  }

  const apiBase = API_BASE_URL.replace(/\/$/, "");

  const casesParams = new URLSearchParams();
  if (searchParams.date_from) casesParams.set("date_from", searchParams.date_from);
  if (searchParams.date_to) casesParams.set("date_to", searchParams.date_to);
  if (searchParams.auth_state) casesParams.set("auth_state", searchParams.auth_state);
  if (searchParams.verdict) casesParams.set("verdict", searchParams.verdict);

  let cases: CaseRecord[] = [];
  let stats: Stats = { total: 0, with_feedback: 0, correct: 0, incorrect: 0, unsure: 0 };
  let userStats: UserStats = { total: 0, new_today: 0, new_7d: 0, active_7d: 0 };
  let users: UserRecord[] = [];
  let metrics: Metrics = {
    total_cases: 0,
    cases_today: 0,
    cases_7d: 0,
    logged_in_cases: 0,
    guest_cases: 0,
    collection_adoption_pct: 0,
    avg_analyses_per_user: 0,
    activation_rate_pct: 0,
    users_with_analysis: 0,
  };

  const casesUrl = `${apiBase}/api/dashboard/cases${casesParams.toString() ? `?${casesParams}` : ""}`;

  try {
    const [casesRes, statsRes, userStatsRes, usersRes, metricsRes] = await Promise.all([
      fetch(casesUrl, { cache: "no-store" }),
      fetch(`${apiBase}/api/dashboard/stats`, { cache: "no-store" }),
      fetch(`${apiBase}/api/dashboard/user-stats`, { cache: "no-store" }),
      fetch(`${apiBase}/api/dashboard/users`, { cache: "no-store" }),
      fetch(`${apiBase}/api/dashboard/metrics`, { cache: "no-store" }),
    ]);
    if (casesRes.ok) cases = await casesRes.json();
    if (statsRes.ok) stats = await statsRes.json();
    if (userStatsRes.ok) userStats = await userStatsRes.json();
    if (usersRes.ok) users = await usersRes.json();
    if (metricsRes.ok) metrics = await metricsRes.json();
  } catch {
    // ignore
  }

  const hasFilters = !!(searchParams.date_from || searchParams.date_to || searchParams.auth_state || searchParams.verdict);

  return (
    <div className="min-h-screen bg-slate-950 p-6 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-10">

        {/* Header */}
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">LegitScore Dashboard</h1>
          <a
            href="/dashboard/submissions"
            className="rounded-full border border-slate-600 bg-slate-800/40 px-4 py-2 text-sm text-slate-300 transition hover:border-emerald-400/40 hover:text-emerald-300"
          >
            Zgłoszenia →
          </a>
        </div>

        {/* ── SEKCJA: UŻYTKOWNICY ── */}
        <section className="space-y-4">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            Użytkownicy
          </h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Zarejestrowani" value={userStats.total} color="slate" />
            <StatCard label="Nowi dziś" value={userStats.new_today} color="emerald" />
            <StatCard label="Nowi 7 dni" value={userStats.new_7d} color="blue" />
            <StatCard label="Aktywni 7 dni" value={userStats.active_7d} color="amber" />
          </div>

          {/* Segment breakdown */}
          {metrics.segments && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-slate-700/60 bg-slate-900/40 p-4 space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Typ użytkownika</p>
                <SegmentBar label="Kolekcjoner" value={metrics.segments.user_type.kolekcjoner ?? 0} total={metrics.segments.survey_completed} />
                <SegmentBar label="Okazjonalny" value={metrics.segments.user_type.okazjonalny_kupujacy ?? 0} total={metrics.segments.survey_completed} />
                <SegmentBar label="Sprzedający" value={metrics.segments.user_type.sprzedajacy ?? 0} total={metrics.segments.survey_completed} />
                <p className="text-[10px] text-slate-600 pt-1">
                  Wypełnili: {metrics.segments.survey_completed} · Pominęli: {metrics.segments.survey_skipped}
                </p>
              </div>
              <div className="rounded-xl border border-slate-700/60 bg-slate-900/40 p-4 space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Rozmiar kolekcji</p>
                <SegmentBar label="0–5" value={metrics.segments.collection_size["0-5"] ?? 0} total={metrics.segments.survey_completed} />
                <SegmentBar label="6–20" value={metrics.segments.collection_size["6-20"] ?? 0} total={metrics.segments.survey_completed} />
                <SegmentBar label="21–50" value={metrics.segments.collection_size["21-50"] ?? 0} total={metrics.segments.survey_completed} />
                <SegmentBar label="50+" value={metrics.segments.collection_size["50+"] ?? 0} total={metrics.segments.survey_completed} />
              </div>
            </div>
          )}

          <div className="overflow-x-auto rounded-xl border border-slate-700 bg-slate-900/50">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-700 bg-slate-800/50 text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-3">Email</th>
                  <th className="px-4 py-3">Rejestracja</th>
                  <th className="px-4 py-3">Typ</th>
                  <th className="px-4 py-3">Kolekcja</th>
                  <th className="px-4 py-3">Analizy</th>
                  <th className="px-4 py-3">Kolekcja (szt.)</th>
                  <th className="px-4 py-3">Ostatnia aktywność</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-6 text-center text-slate-500">
                      Brak użytkowników
                    </td>
                  </tr>
                ) : (
                  users.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-800/30">
                      <td className="px-4 py-3 text-xs text-slate-200">
                        {u.email}
                        {u.is_admin && (
                          <span className="ml-2 rounded-full bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-300">
                            admin
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                        {u.created_at ? formatDate(u.created_at) : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <UserTypeBadge userType={u.user_type} />
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400">
                        {u.collection_size_range ?? <span className="text-slate-700">—</span>}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {u.analysis_count > 0 ? (
                          <span className="text-emerald-300">{u.analysis_count}</span>
                        ) : (
                          <span className="text-slate-600">0</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {u.collection_count > 0 ? (
                          <span className="text-blue-300">{u.collection_count}</span>
                        ) : (
                          <span className="text-slate-600">0</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs">
                        {u.last_activity_at ? (
                          <span className="text-slate-400">{formatDate(u.last_activity_at)}</span>
                        ) : (
                          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-500">
                            Nowy użytkownik
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs font-mono text-slate-600">
                        {u.id.slice(0, 8)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── SEKCJA: METRYKI ── */}
        <section className="space-y-4">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            Metryki
          </h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <MetricCard
              label="Aktywacja (% użytkowników z ≥1 analizą)"
              value={`${metrics.activation_rate_pct}%`}
              sub={`${metrics.users_with_analysis} aktywnych użytkowników`}
            />
            <MetricCard
              label="Śr. analiz / aktywny użytkownik"
              value={String(metrics.avg_analyses_per_user)}
              sub={`na ${metrics.users_with_analysis} aktywnych`}
            />
            <MetricCard
              label="Kolekcja adoption"
              value={`${metrics.collection_adoption_pct}%`}
              sub="użytkowników z kolekcją"
            />
            <MetricCard
              label="Analizy: zalogowani vs goście"
              value={`${metrics.logged_in_cases} / ${metrics.guest_cases}`}
              sub={metrics.total_cases > 0
                ? `${Math.round(metrics.logged_in_cases / metrics.total_cases * 100)}% / ${Math.round(metrics.guest_cases / metrics.total_cases * 100)}%`
                : "—"
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
            <StatCard label="Analiz dziś" value={metrics.cases_today} color="emerald" />
            <StatCard label="Analiz 7 dni" value={metrics.cases_7d} color="blue" />
            <StatCard label="Analiz łącznie" value={metrics.total_cases} color="slate" />
          </div>
        </section>

        {/* ── SEKCJA: RAPORTY ── */}
        <section className="space-y-4">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            Raporty
          </h2>

          {/* Report stats (unfiltered) */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <StatCard label="Wszystkie" value={stats.total} color="slate" />
            <StatCard label="Z feedbackiem" value={stats.with_feedback} color="blue" />
            <StatCard label="Poprawne" value={stats.correct} color="emerald" />
            <StatCard label="Niepoprawne" value={stats.incorrect} color="red" />
            <StatCard label="Nie wiem" value={stats.unsure} color="amber" />
          </div>

          {/* Filters */}
          <div className="flex flex-col gap-3 rounded-xl border border-slate-700/60 bg-slate-900/40 p-4 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-xs text-slate-500">
              {hasFilters ? (
                <>
                  Filtrowanie aktywne ·{" "}
                  <a href="/dashboard" className="text-emerald-400 hover:underline">
                    wyczyść
                  </a>
                </>
              ) : (
                "Filtruj raporty"
              )}
            </span>
            <Suspense>
              <DashboardFilters />
            </Suspense>
          </div>

          {/* Cases table */}
          <div className="overflow-x-auto rounded-xl border border-slate-700 bg-slate-900/50">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-700 bg-slate-800/50 text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-3">Data</th>
                  <th className="px-4 py-3">Case ID</th>
                  <th className="px-4 py-3">Email</th>
                  <th className="px-4 py-3">Auth</th>
                  <th className="px-4 py-3">SKU</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3">Werdykt</th>
                  <th className="px-4 py-3">Pewność</th>
                  <th className="px-4 py-3">Ocena</th>
                  <th className="px-4 py-3">Feedback</th>
                  <th className="px-4 py-3">Akcje</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {cases.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="px-4 py-8 text-center text-slate-500">
                      {hasFilters ? "Brak wyników dla wybranych filtrów" : "Brak danych w bazie"}
                    </td>
                  </tr>
                ) : (
                  cases.map((c) => (
                    <tr key={c.case_id} className="hover:bg-slate-800/30">
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                        {c.created_at ? formatDate(c.created_at) : "—"}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {c.case_id.slice(0, 8)}...
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-300">
                        {c.email || <span className="text-slate-500">—</span>}
                      </td>
                      <td className="px-4 py-3">
                        <AuthBadge authState={c.auth_state} />
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-emerald-300">
                        {c.sku || <span className="text-slate-500">—</span>}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400">
                        {c.model?.replace("models/", "") || "—"}
                      </td>
                      <td className="px-4 py-3">
                        <VerdictBadge category={c.verdict_category} />
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {c.confidence_percent ? `${c.confidence_percent}%` : "—"}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {c.rating ? (
                          <span title={`Ocena: ${c.rating}/5`}>
                            {"⚽".repeat(c.rating)}
                            <span className="opacity-30">{"⚽".repeat(5 - c.rating)}</span>
                          </span>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <FeedbackBadge feedback={c.feedback} />
                      </td>
                      <td className="px-4 py-3">
                        <a
                          href={`/case/${c.case_id}`}
                          className="text-xs text-emerald-400 hover:underline"
                        >
                          Zobacz
                        </a>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colors: Record<string, string> = {
    slate: "bg-slate-800 border-slate-600",
    blue: "bg-blue-900/30 border-blue-500/40",
    emerald: "bg-emerald-900/30 border-emerald-500/40",
    red: "bg-red-900/30 border-red-500/40",
    amber: "bg-amber-900/30 border-amber-500/40",
  };
  return (
    <div className={`rounded-xl border p-4 ${colors[color] || colors.slate}`}>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-slate-400">{label}</div>
    </div>
  );
}

function MetricCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-4">
      <div className="text-xl font-bold text-emerald-300">{value}</div>
      <div className="text-xs font-medium text-slate-200">{label}</div>
      <div className="mt-0.5 text-[10px] text-slate-500">{sub}</div>
    </div>
  );
}

function UserTypeBadge({ userType }: { userType: string | null }) {
  if (!userType) return <span className="text-slate-700 text-xs">—</span>;
  const map: Record<string, { label: string; cls: string }> = {
    kolekcjoner: { label: "Kolekcjoner", cls: "bg-purple-500/15 text-purple-300" },
    okazjonalny_kupujacy: { label: "Okazjonalny", cls: "bg-blue-500/15 text-blue-300" },
    sprzedajacy: { label: "Sprzedający", cls: "bg-amber-500/15 text-amber-300" },
  };
  const m = map[userType] ?? { label: userType, cls: "bg-slate-700 text-slate-300" };
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${m.cls}`}>
      {m.label}
    </span>
  );
}

function SegmentBar({ label, value, total }: { label: string; value: number; total: number }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 text-xs text-slate-400">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-slate-800">
        <div
          className="h-1.5 rounded-full bg-emerald-500/60"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right text-[11px] text-slate-500">{value}</span>
    </div>
  );
}

function AuthBadge({ authState }: { authState: string | null }) {
  if (!authState) return <span className="text-xs text-slate-600">—</span>;
  if (authState === "logged_in") {
    return (
      <span className="inline-block rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
        login
      </span>
    );
  }
  return (
    <span className="inline-block rounded-full bg-slate-500/20 px-2 py-0.5 text-[10px] font-medium text-slate-400">
      gość
    </span>
  );
}

function VerdictBadge({ category }: { category: string | null }) {
  if (!category) return <span className="text-xs text-slate-500">—</span>;

  const colors: Record<string, string> = {
    meczowa: "bg-purple-500/20 text-purple-300 border-purple-400/40",
    oryginalna_sklepowa: "bg-emerald-500/20 text-emerald-300 border-emerald-400/40",
    oficjalna_replika: "bg-blue-500/20 text-blue-300 border-blue-400/40",
    podrobka: "bg-red-500/20 text-red-300 border-red-400/40",
    edycja_limitowana: "bg-amber-500/20 text-amber-300 border-amber-400/40",
    treningowa_custom: "bg-slate-500/20 text-slate-300 border-slate-400/40",
  };

  const labels: Record<string, string> = {
    meczowa: "Meczowa",
    oryginalna_sklepowa: "Oryginalna",
    oficjalna_replika: "Replika",
    podrobka: "Podróbka",
    edycja_limitowana: "Limitowana",
    treningowa_custom: "Treningowa",
  };

  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${
        colors[category] || "bg-slate-700 text-slate-300"
      }`}
    >
      {labels[category] || category}
    </span>
  );
}

function FeedbackBadge({ feedback }: { feedback: string | null }) {
  if (!feedback) return <span className="text-xs text-slate-500">—</span>;

  const styles: Record<string, { bg: string; label: string }> = {
    correct: { bg: "bg-emerald-500/20 text-emerald-300", label: "Poprawny" },
    incorrect: { bg: "bg-red-500/20 text-red-300", label: "Niepoprawny" },
    unsure: { bg: "bg-amber-500/20 text-amber-300", label: "Nie wiem" },
  };

  const style = styles[feedback] || { bg: "bg-slate-700", label: feedback };

  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${style.bg}`}>
      {style.label}
    </span>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("pl-PL", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
