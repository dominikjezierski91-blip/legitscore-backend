export const dynamic = "force-dynamic";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

type Submission = {
  id: string;
  created_at: string | null;
  status: string;
  type: string;
  message: string;
  email: string | null;
  auth_state: string | null;
  source_page: string | null;
  app_section: string | null;
  report_id: string | null;
  analysis_id: string | null;
  shirt_id: string | null;
};

export default async function SubmissionsPage() {
  if (!API_BASE_URL) {
    return <div className="p-8 text-amber-200">Brak konfiguracji NEXT_PUBLIC_API_BASE_URL.</div>;
  }

  const apiBase = API_BASE_URL.replace(/\/$/, "");
  let submissions: Submission[] = [];

  try {
    const res = await fetch(`${apiBase}/api/support`, { cache: "no-store" });
    if (res.ok) submissions = await res.json();
  } catch {}

  const nowe = submissions.filter((s) => s.status === "nowe").length;
  const wTrakcie = submissions.filter((s) => s.status === "w_trakcie").length;
  const zamkniete = submissions.filter((s) => s.status === "zamkniete").length;

  return (
    <div className="min-h-screen bg-slate-950 p-6 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <a href="/dashboard" className="text-xs text-slate-500 hover:text-slate-300">← Dashboard</a>
            <h1 className="mt-1 text-2xl font-bold">Zgłoszenia</h1>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 md:grid-cols-4">
          <StatCard label="Wszystkie" value={submissions.length} color="slate" />
          <StatCard label="Nowe" value={nowe} color="blue" />
          <StatCard label="W trakcie" value={wTrakcie} color="amber" />
          <StatCard label="Zamknięte" value={zamkniete} color="emerald" />
        </div>

        {/* Table */}
        <div className="overflow-x-auto rounded-xl border border-slate-700 bg-slate-900/50">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-700 bg-slate-800/50 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Data</th>
                <th className="px-4 py-3">Typ</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Źródło</th>
                <th className="px-4 py-3">Powiązanie</th>
                <th className="px-4 py-3">Wiadomość</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {submissions.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                    Brak zgłoszeń
                  </td>
                </tr>
              ) : (
                submissions.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-800/30">
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                      {s.created_at ? formatDate(s.created_at) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <TypeBadge type={s.type} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={s.status} />
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-300">
                      {s.email || <span className="text-slate-500">—</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400">
                      {s.app_section || s.source_page || <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-4 py-3 font-mono text-[11px] text-slate-500">
                      {s.report_id
                        ? s.report_id.slice(0, 8)
                        : s.analysis_id
                        ? s.analysis_id.slice(0, 8)
                        : <span className="text-slate-700">—</span>}
                    </td>
                    <td className="max-w-xs px-4 py-3 text-xs text-slate-300">
                      <span className="line-clamp-2">{s.message}</span>
                    </td>
                    <td className="px-4 py-3">
                      <a
                        href={`/dashboard/submissions/${s.id}`}
                        className="text-xs text-emerald-400 hover:underline whitespace-nowrap"
                      >
                        Otwórz →
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
    amber: "bg-amber-900/30 border-amber-500/40",
    emerald: "bg-emerald-900/30 border-emerald-500/40",
  };
  return (
    <div className={`rounded-xl border p-4 ${colors[color] || colors.slate}`}>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-slate-400">{label}</div>
    </div>
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
    <span className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${m.cls}`}>
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
    <span className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${m.cls}`}>
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
