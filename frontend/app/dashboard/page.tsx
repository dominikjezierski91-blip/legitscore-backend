export const dynamic = "force-dynamic";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

type CaseRecord = {
  case_id: string;
  created_at: string | null;
  email: string | null;
  consent_at: string | null;
  model: string | null;
  prompt_version: string | null;
  verdict_category: string | null;
  confidence_percent: string | null;
  feedback: string | null;
  feedback_at: string | null;
  feedback_comment: string | null;
};

type Stats = {
  total: number;
  with_feedback: number;
  correct: number;
  incorrect: number;
  unsure: number;
};

export default async function DashboardPage() {
  if (!API_BASE_URL) {
    return (
      <div className="p-8 text-amber-200">
        Brak konfiguracji NEXT_PUBLIC_API_BASE_URL.
      </div>
    );
  }

  const apiBase = API_BASE_URL.replace(/\/$/, "");

  let cases: CaseRecord[] = [];
  let stats: Stats = { total: 0, with_feedback: 0, correct: 0, incorrect: 0, unsure: 0 };

  try {
    const [casesRes, statsRes] = await Promise.all([
      fetch(`${apiBase}/api/dashboard/cases`, { cache: "no-store" }),
      fetch(`${apiBase}/api/dashboard/stats`, { cache: "no-store" }),
    ]);
    if (casesRes.ok) cases = await casesRes.json();
    if (statsRes.ok) stats = await statsRes.json();
  } catch {
    // ignore
  }

  return (
    <div className="min-h-screen bg-slate-950 p-6 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <h1 className="text-2xl font-bold">LegitScore Dashboard</h1>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          <StatCard label="Wszystkie" value={stats.total} color="slate" />
          <StatCard label="Z feedbackiem" value={stats.with_feedback} color="blue" />
          <StatCard label="Poprawne" value={stats.correct} color="emerald" />
          <StatCard label="Niepoprawne" value={stats.incorrect} color="red" />
          <StatCard label="Nie wiem" value={stats.unsure} color="amber" />
        </div>

        {/* Table */}
        <div className="overflow-x-auto rounded-xl border border-slate-700 bg-slate-900/50">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-700 bg-slate-800/50 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Data</th>
                <th className="px-4 py-3">Case ID</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Model</th>
                <th className="px-4 py-3">Werdykt</th>
                <th className="px-4 py-3">Pewność</th>
                <th className="px-4 py-3">Feedback</th>
                <th className="px-4 py-3">Akcje</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {cases.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                    Brak danych w bazie
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
                    <td className="px-4 py-3 text-xs text-slate-400">
                      {c.model?.replace("models/", "") || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <VerdictBadge category={c.verdict_category} />
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {c.confidence_percent ? `${c.confidence_percent}%` : "—"}
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
