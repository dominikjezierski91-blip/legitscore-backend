"use client";

import { useState } from "react";
import { useAuth } from "@/components/auth/auth-provider";
import { submitSupport } from "@/lib/api";
import { CheckCircle2, ChevronLeft } from "lucide-react";
import { cn } from "@/lib/utils";

const TOPICS = [
  { value: "sugestia", emoji: "💡", label: "Pomysł na ulepszenie", placeholder: "Opisz swój pomysł — co chciałbyś, żeby działało lepiej lub inaczej?" },
  { value: "problem", emoji: "🐛", label: "Zgłoś błąd", placeholder: "Opisz problem: co się stało, kiedy i co robiłeś w tym czasie?" },
  { value: "pytanie", emoji: "❓", label: "Pytanie o aplikację", placeholder: "Zadaj pytanie — postaramy się odpowiedzieć jak najszybciej." },
  { value: "inne", emoji: "📧", label: "Inne", placeholder: "Napisz, w czym możemy pomóc." },
];

export default function ContactPage() {
  const { user } = useAuth();
  const [step, setStep] = useState<1 | 2>(1);
  const [topic, setTopic] = useState<(typeof TOPICS)[0] | null>(null);
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState(user?.email ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  function selectTopic(t: (typeof TOPICS)[0]) {
    setTopic(t);
    setStep(2);
  }

  function goBack() {
    setStep(1);
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!message.trim()) { setError("Opisz swój temat — pole nie może być puste."); return; }
    if (!email.trim()) { setError("Podaj adres email."); return; }
    setSubmitting(true);
    try {
      await submitSupport({
        type: topic?.value ?? "inne",
        message: message.trim(),
        email: email.trim(),
        wants_reply: true,
        user_id: user?.id ?? undefined,
        auth_state: user ? "logged_in" : "guest",
        app_section: "contact_page",
        source_page: "/contact",
      });
      setSuccess(true);
    } catch (err: any) {
      setError(err.message || "Nie udało się wysłać wiadomości. Spróbuj ponownie.");
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <div className="flex flex-1 items-center justify-center py-16 px-4">
        <div className="w-full max-w-sm text-center space-y-5">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/15 ring-1 ring-emerald-500/30">
            <CheckCircle2 className="h-8 w-8 text-emerald-400" />
          </div>
          <div className="space-y-1">
            <h1 className="text-xl font-semibold text-slate-50">Dziękujemy!</h1>
            <p className="text-sm text-slate-400">
              Odpowiemy na podany adres email.
            </p>
          </div>
          <button
            onClick={() => { setSuccess(false); setStep(1); setTopic(null); setMessage(""); setEmail(user?.email ?? ""); }}
            className="text-xs text-slate-500 hover:text-slate-300 transition"
          >
            Wyślij kolejną wiadomość
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col items-center py-10 px-4">
      <div className="w-full max-w-lg space-y-6">

        {/* Header */}
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight text-slate-50">Kontakt</h1>
          <p className="text-xs text-muted-foreground">
            Napisz do nas — postaramy się odpowiedzieć jak najszybciej.
          </p>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-2">
          {[1, 2].map((s) => (
            <div key={s} className="flex items-center gap-2">
              <div className={cn(
                "flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold transition-all duration-300",
                step >= s
                  ? "bg-emerald-500 text-slate-950"
                  : "bg-slate-800 text-slate-500"
              )}>
                {s}
              </div>
              {s < 2 && (
                <div className={cn(
                  "h-px w-8 transition-all duration-300",
                  step > s ? "bg-emerald-500" : "bg-slate-700"
                )} />
              )}
            </div>
          ))}
          <span className="ml-2 text-[11px] text-slate-500">
            {step === 1 ? "Wybierz temat" : "Opisz szczegóły"}
          </span>
        </div>

        {/* Step 1 — topic selection */}
        <div className={cn(
          "transition-all duration-300",
          step === 1 ? "opacity-100 translate-x-0" : "hidden"
        )}>
          <div className="grid grid-cols-2 gap-3">
            {TOPICS.map((t) => (
              <button
                key={t.value}
                onClick={() => selectTopic(t)}
                className="glass-card flex flex-col items-start gap-3 p-4 text-left transition hover:border-emerald-500/30 hover:bg-emerald-500/5 active:scale-[0.98]"
              >
                <span className="text-2xl">{t.emoji}</span>
                <span className="text-sm font-medium text-slate-200 leading-snug">{t.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Step 2 — form */}
        <div className={cn(
          "transition-all duration-300",
          step === 2 ? "opacity-100 translate-x-0" : "hidden"
        )}>
          <form onSubmit={handleSubmit} className="glass-card p-5 space-y-4">
            {/* Topic badge + back */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xl">{topic?.emoji}</span>
                <span className="text-sm font-medium text-slate-200">{topic?.label}</span>
              </div>
              <button
                type="button"
                onClick={goBack}
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Zmień
              </button>
            </div>

            <div className="border-t border-border/30" />

            {/* Message */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-400">
                {topic?.value === "sugestia" ? "Twój pomysł" :
                 topic?.value === "problem" ? "Opis problemu" :
                 topic?.value === "pytanie" ? "Twoje pytanie" : "Wiadomość"}
              </label>
              <textarea
                value={message}
                onChange={(e) => { setMessage(e.target.value); setError(null); }}
                rows={4}
                placeholder={topic?.placeholder ?? "Opisz swój temat…"}
                className="w-full resize-none rounded-xl border border-border/60 bg-slate-900/60 px-3 py-2.5 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/20"
              />
            </div>

            {/* Email */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-400">Adres email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => { setEmail(e.target.value); setError(null); }}
                placeholder="twoj@email.com"
                className="w-full rounded-xl border border-border/60 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/20"
              />
              <p className="text-[10px] text-slate-600">Potrzebny do odpowiedzi — nie wysyłamy spamu.</p>
            </div>

            {error && (
              <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-full bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 shadow-md shadow-emerald-500/20 transition hover:bg-emerald-400 disabled:opacity-60"
            >
              {submitting ? "Wysyłanie…" : "Wyślij →"}
            </button>
          </form>
        </div>

      </div>
    </div>
  );
}
