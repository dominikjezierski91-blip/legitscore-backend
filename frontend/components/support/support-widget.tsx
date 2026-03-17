"use client";

import { useState } from "react";
import { X, MessageCircle, CheckCircle2 } from "lucide-react";
import { submitSupport, type SupportPayload } from "@/lib/api";
import { useAuth } from "@/components/auth/auth-provider";
import { cn } from "@/lib/utils";

const TYPE_OPTIONS = [
  { value: "pytanie", label: "Pytanie do raportu" },
  { value: "problem", label: "Zgłoszenie problemu" },
  { value: "sugestia", label: "Sugestia" },
  { value: "inne", label: "Inne" },
];

interface Props {
  reportId?: string;
  analysisId?: string;
  appSection?: string;
}

export function SupportWidget({ reportId, analysisId, appSection = "report" }: Props) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [preselectedType, setPreselectedType] = useState<string | null>(null);

  function openWith(type: string) {
    setPreselectedType(type);
    setOpen(true);
  }

  return (
    <>
      <div className="space-y-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-200">
            Masz pytanie do tego raportu?
          </p>
          <p className="mt-1 text-[11px] text-slate-500">
            Zgłoś problem, zadaj pytanie lub podziel się sugestią. Odpowiemy mailowo, jeśli będzie to potrzebne.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => openWith("pytanie")}
            className="rounded-full border border-slate-600/60 bg-slate-800/40 px-3 py-1.5 text-[11px] text-slate-300 transition hover:border-emerald-400/40 hover:text-emerald-300"
          >
            Zadaj pytanie
          </button>
          <button
            onClick={() => openWith("problem")}
            className="rounded-full border border-slate-600/60 bg-slate-800/40 px-3 py-1.5 text-[11px] text-slate-300 transition hover:border-amber-400/40 hover:text-amber-300"
          >
            Zgłoś problem
          </button>
          <button
            onClick={() => openWith("sugestia")}
            className="rounded-full border border-slate-600/60 bg-slate-800/40 px-3 py-1.5 text-[11px] text-slate-300 transition hover:border-slate-400/40 hover:text-slate-200"
          >
            Podziel się sugestią
          </button>
        </div>
      </div>

      {open && (
        <SupportModal
          preselectedType={preselectedType}
          user={user}
          reportId={reportId}
          analysisId={analysisId}
          appSection={appSection}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

interface ModalProps {
  preselectedType: string | null;
  user: any;
  reportId?: string;
  analysisId?: string;
  appSection?: string;
  onClose: () => void;
}

function SupportModal({ preselectedType, user, reportId, analysisId, appSection, onClose }: ModalProps) {
  const [type, setType] = useState(preselectedType ?? "pytanie");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState(user?.email ?? "");
  const [wantsReply, setWantsReply] = useState(true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  function validate() {
    const e: Record<string, string> = {};
    if (!type) e.type = "Wybierz typ zgłoszenia.";
    if (!message.trim()) e.message = "Wiadomość jest wymagana.";
    if (message.length > 1000) e.message = "Wiadomość nie może przekraczać 1000 znaków.";
    if (!email.trim()) e.email = "Email jest wymagany.";
    return e;
  }

  async function handleSubmit() {
    const e = validate();
    if (Object.keys(e).length > 0) { setErrors(e); return; }

    setSubmitting(true);
    try {
      const payload: SupportPayload = {
        type,
        message: message.trim(),
        email: email.trim(),
        wants_reply: wantsReply,
        user_id: user?.id ?? undefined,
        auth_state: user ? "logged_in" : "guest",
        source_page: typeof window !== "undefined" ? window.location.pathname : undefined,
        current_url: typeof window !== "undefined" ? window.location.href : undefined,
        app_section: appSection,
        report_id: reportId ?? undefined,
        analysis_id: analysisId ?? undefined,
      };
      await submitSupport(payload);
      setSuccess(true);
    } catch (err: any) {
      setErrors({ submit: err.message || "Nie udało się wysłać zgłoszenia." });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-4 sm:items-center"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-md rounded-2xl border border-border/60 bg-slate-950 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-full p-1 text-slate-500 transition hover:text-slate-300"
        >
          <X className="h-4 w-4" />
        </button>

        {success ? (
          <div className="space-y-4 text-center py-2">
            <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-400" />
            <div>
              <h2 className="text-base font-semibold text-slate-50">Dziękujemy. Twoje zgłoszenie zostało zapisane.</h2>
              <p className="mt-1 text-xs text-slate-500">Jeśli będzie to potrzebne, skontaktujemy się mailowo.</p>
            </div>
            <button
              onClick={onClose}
              className="w-full rounded-full bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400"
            >
              Zamknij
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="pr-6">
              <h2 className="text-base font-semibold text-slate-50">Napisz do nas</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Zgłoszenie zostanie przejrzane przez zespół LegitScore. Nie jest to czat na żywo.
              </p>
            </div>

            {/* Typ */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-400">Typ zgłoszenia</label>
              <select
                value={type}
                onChange={(e) => { setType(e.target.value); setErrors((v) => { const n = {...v}; delete n.type; return n; }); }}
                className={cn(
                  "w-full rounded-lg border bg-slate-900/60 px-3 py-2 text-sm text-slate-100 outline-none",
                  errors.type ? "border-red-500/60" : "border-border/60 focus:border-emerald-500/40"
                )}
              >
                {TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              {errors.type && <p className="text-[11px] text-red-400">{errors.type}</p>}
            </div>

            {/* Wiadomość */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-slate-400">Wiadomość</label>
                <span className={cn("text-[10px]", message.length > 1000 ? "text-red-400" : "text-slate-600")}>
                  {message.length} / 1000
                </span>
              </div>
              <textarea
                value={message}
                onChange={(e) => { setMessage(e.target.value); setErrors((v) => { const n = {...v}; delete n.message; return n; }); }}
                rows={4}
                placeholder="Opisz swoje pytanie, problem lub sugestię..."
                className={cn(
                  "w-full resize-none rounded-lg border bg-slate-900/60 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500",
                  errors.message ? "border-red-500/60" : "border-border/60 focus:border-emerald-500/40"
                )}
              />
              {errors.message && <p className="text-[11px] text-red-400">{errors.message}</p>}
            </div>

            {/* Email */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-400">
                Email {!user && <span className="text-red-400">*</span>}
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value); setErrors((v) => { const n = {...v}; delete n.email; return n; }); }}
                placeholder="twoj@email.com"
                className={cn(
                  "w-full rounded-lg border bg-slate-900/60 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500",
                  errors.email ? "border-red-500/60" : "border-border/60 focus:border-emerald-500/40"
                )}
              />
              {errors.email && <p className="text-[11px] text-red-400">{errors.email}</p>}
            </div>

            {/* Chcę odpowiedź */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={wantsReply}
                onChange={(e) => setWantsReply(e.target.checked)}
                className="h-3.5 w-3.5 rounded accent-emerald-500"
              />
              <span className="text-xs text-slate-400">Chcę otrzymać odpowiedź mailowo</span>
            </label>

            {errors.submit && (
              <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{errors.submit}</p>
            )}

            <div className="flex gap-2 pt-1">
              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="flex-1 rounded-full bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400 disabled:opacity-60"
              >
                {submitting ? "Wysyłanie..." : "Wyślij zgłoszenie"}
              </button>
              <button
                onClick={onClose}
                className="rounded-full border border-slate-600 px-4 py-2.5 text-sm text-slate-300 transition hover:border-slate-500"
              >
                Anuluj
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
