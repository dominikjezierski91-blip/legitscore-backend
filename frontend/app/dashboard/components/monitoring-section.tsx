"use client";

import { useEffect, useState } from "react";
import { Bug, ChevronDown, ChevronUp, Loader2, CheckCircle2, Clock, Circle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type Ticket = {
  id: string;
  priorytet: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  typ: string;
  opis: string;
  data: string;
  status: string;
  case_id: string | null;
  sugerowane_rozwiazanie: string;
};

type TicketsResponse = {
  tickets: Ticket[];
  open_count: number;
  critical_count: number;
};

const PRIORITY_META: Record<string, { badge: string }> = {
  CRITICAL: { badge: "bg-red-500/20 text-red-300 border border-red-500/30" },
  HIGH:     { badge: "bg-orange-500/20 text-orange-300 border border-orange-500/30" },
  MEDIUM:   { badge: "bg-yellow-500/20 text-yellow-300 border border-yellow-500/30" },
  LOW:      { badge: "bg-slate-500/20 text-slate-400 border border-slate-600/40" },
};

const STATUS_META: Record<string, { icon: React.ReactNode; color: string }> = {
  "Nowy":       { icon: <Circle className="h-3 w-3" />,      color: "text-slate-400" },
  "W trakcie":  { icon: <Clock className="h-3 w-3" />,       color: "text-yellow-400" },
  "Rozwiązany": { icon: <CheckCircle2 className="h-3 w-3" />, color: "text-emerald-400" },
};

type Filter = "Wszystkie" | "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

async function apiPost(path: string, body?: object) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export function MonitoringSection() {
  const [data, setData] = useState<TicketsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("Wszystkie");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [fixLoading, setFixLoading] = useState<Record<string, boolean>>({});
  const [fixProposals, setFixProposals] = useState<Record<string, string>>({});
  const [fixErrors, setFixErrors] = useState<Record<string, string>>({});
  const [statusLoading, setStatusLoading] = useState<Record<string, boolean>>({});

  async function fetchTickets() {
    try {
      const res = await fetch(`${API_BASE}/api/monitoring/tickets`);
      if (res.ok) setData(await res.json());
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchTickets(); }, []);

  async function handleResolve(id: string) {
    setFixLoading((p) => ({ ...p, [id]: true }));
    setFixErrors((p) => ({ ...p, [id]: "" }));
    try {
      const r = await apiPost(`/api/monitoring/tickets/${id}/resolve`);
      setFixProposals((p) => ({ ...p, [id]: r.fix_proposal }));
      setExpanded((p) => ({ ...p, [id]: true }));
    } catch (e: any) {
      setFixErrors((p) => ({ ...p, [id]: e.message ?? "Błąd API" }));
    } finally {
      setFixLoading((p) => ({ ...p, [id]: false }));
    }
  }

  async function handleStatus(id: string, status: string) {
    setStatusLoading((p) => ({ ...p, [id]: true }));
    try {
      await apiPost(`/api/monitoring/tickets/${id}/status`, { status });
      await fetchTickets();
    } catch (e: any) {
      alert(`Błąd: ${e.message}`);
    } finally {
      setStatusLoading((p) => ({ ...p, [id]: false }));
    }
  }

  const tickets = data?.tickets ?? [];
  const filters: Filter[] = ["Wszystkie", "CRITICAL", "HIGH", "MEDIUM", "LOW"];
  const filtered = filter === "Wszystkie" ? tickets : tickets.filter((t) => t.priorytet === filter);

  return (
    <section id="monitoring" className="space-y-4">
      {/* Nagłówek sekcji */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            Monitoring
          </h2>
          {data && data.open_count > 0 && (
            <span className="text-[10px] text-slate-500">
              — {data.open_count} otwartych
              {data.critical_count > 0 && (
                <span className="ml-1 text-red-400 font-medium">
                  ({data.critical_count} CRITICAL)
                </span>
              )}
            </span>
          )}
        </div>
        <button
          onClick={fetchTickets}
          className="text-xs text-slate-600 hover:text-slate-400 transition"
        >
          ↻ odśwież
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-2 py-6 text-slate-500 text-xs">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Ładowanie ticketów...
        </div>
      )}

      {!loading && tickets.length === 0 && (
        <div className="rounded-xl border border-slate-700/40 bg-slate-900/30 px-4 py-6 text-center text-xs text-slate-600">
          Brak otwartych ticketów.
        </div>
      )}

      {!loading && tickets.length > 0 && (
        <>
          {/* Filtry */}
          <div className="flex flex-wrap gap-1.5">
            {filters.map((f) => {
              const count = f === "Wszystkie"
                ? tickets.filter((t) => t.status !== "Rozwiązany").length
                : tickets.filter((t) => t.priorytet === f && t.status !== "Rozwiązany").length;
              return (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={cn(
                    "rounded-full px-2.5 py-1 text-[11px] font-medium transition border",
                    filter === f
                      ? "bg-slate-700 text-slate-100 border-slate-500"
                      : "bg-slate-900/40 text-slate-500 border-slate-700/50 hover:border-slate-500 hover:text-slate-300"
                  )}
                >
                  {f} {count > 0 && <span className="opacity-50">({count})</span>}
                </button>
              );
            })}
          </div>

          {/* Lista ticketów */}
          <div className="space-y-2">
            {filtered.length === 0 && (
              <p className="text-xs text-slate-600 py-2">Brak ticketów w tej kategorii.</p>
            )}
            {filtered.map((ticket) => {
              const pm = PRIORITY_META[ticket.priorytet] ?? PRIORITY_META.LOW;
              const sm = STATUS_META[ticket.status] ?? STATUS_META["Nowy"];
              const isResolved = ticket.status === "Rozwiązany";
              const hasFix = !!fixProposals[ticket.id];
              const isExpanded = expanded[ticket.id];

              return (
                <div
                  key={ticket.id}
                  className={cn(
                    "rounded-xl border bg-slate-900/50 transition",
                    isResolved
                      ? "border-slate-700/30 opacity-40"
                      : ticket.priorytet === "CRITICAL"
                      ? "border-red-500/25"
                      : ticket.priorytet === "HIGH"
                      ? "border-orange-500/15"
                      : "border-slate-700/50"
                  )}
                >
                  <div className="p-4 space-y-2.5">
                    {/* Górny wiersz */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wide", pm.badge)}>
                        {ticket.priorytet}
                      </span>
                      <span className="text-[11px] font-mono text-slate-500">{ticket.id}</span>
                      <span className="text-slate-700">·</span>
                      <span className="text-[11px] text-slate-500 capitalize">{ticket.typ}</span>
                      <span className="ml-auto text-[10px] text-slate-600">{ticket.data}</span>
                    </div>

                    {/* Opis */}
                    <p className="text-sm text-slate-200 leading-relaxed">{ticket.opis}</p>

                    {ticket.case_id && (
                      <p className="text-[11px] text-slate-500">
                        Case: <span className="font-mono text-slate-400">{ticket.case_id}</span>
                      </p>
                    )}

                    {/* Sugestia */}
                    <div className="rounded-lg bg-slate-800/50 px-3 py-2 text-[11px] text-slate-400 leading-relaxed border border-slate-700/30">
                      <span className="text-slate-500 font-medium">Sugestia: </span>
                      {ticket.sugerowane_rozwiazanie}
                    </div>

                    {/* Akcje */}
                    <div className="flex items-center gap-2 flex-wrap pt-0.5">
                      <div className={cn("flex items-center gap-1 text-[11px]", sm.color)}>
                        {sm.icon} {ticket.status}
                      </div>
                      <div className="ml-auto flex items-center gap-2">
                        {!isResolved && (
                          <button
                            onClick={() => handleResolve(ticket.id)}
                            disabled={fixLoading[ticket.id]}
                            className="flex items-center gap-1.5 rounded-full bg-slate-700/50 px-2.5 py-1 text-[11px] text-slate-300 transition hover:bg-slate-600/60 disabled:opacity-50 border border-slate-600/40"
                          >
                            {fixLoading[ticket.id] ? <Loader2 className="h-3 w-3 animate-spin" /> : <Bug className="h-3 w-3" />}
                            {fixLoading[ticket.id] ? "Analizuję..." : "Rozwiąż z AI"}
                          </button>
                        )}
                        {!isResolved && (
                          <button
                            onClick={() => handleStatus(ticket.id, "Rozwiązany")}
                            disabled={statusLoading[ticket.id]}
                            className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] text-emerald-300 transition hover:bg-emerald-500/20 disabled:opacity-50 border border-emerald-500/20"
                          >
                            {statusLoading[ticket.id] ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
                            Rozwiązany
                          </button>
                        )}
                        {ticket.status === "Nowy" && (
                          <button
                            onClick={() => handleStatus(ticket.id, "W trakcie")}
                            disabled={statusLoading[ticket.id]}
                            className="text-[11px] text-slate-600 hover:text-slate-400 transition"
                          >
                            W trakcie
                          </button>
                        )}
                        {isResolved && (
                          <button
                            onClick={() => handleStatus(ticket.id, "Nowy")}
                            disabled={statusLoading[ticket.id]}
                            className="text-[11px] text-slate-600 hover:text-slate-400 transition"
                          >
                            Przywróć
                          </button>
                        )}
                        {hasFix && (
                          <button
                            onClick={() => setExpanded((p) => ({ ...p, [ticket.id]: !p[ticket.id] }))}
                            className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-300 transition"
                          >
                            {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                            Fix AI
                          </button>
                        )}
                      </div>
                    </div>

                    {fixErrors[ticket.id] && (
                      <p className="text-[11px] text-red-400 rounded-lg bg-red-500/10 px-3 py-1.5">
                        {fixErrors[ticket.id]}
                      </p>
                    )}
                  </div>

                  {/* Rozwinięty fix */}
                  {hasFix && isExpanded && (
                    <div className="border-t border-slate-700/50 px-4 py-3">
                      <div className="flex items-center gap-2 mb-2">
                        <AlertCircle className="h-3 w-3 text-slate-500" />
                        <span className="text-[11px] font-medium text-slate-400">Propozycja fixa (Claude)</span>
                      </div>
                      <pre className="whitespace-pre-wrap text-[11px] text-slate-300 leading-relaxed font-mono bg-slate-800/60 rounded-lg p-3 border border-slate-700/40 overflow-x-auto">
                        {fixProposals[ticket.id]}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}
