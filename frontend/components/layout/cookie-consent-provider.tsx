"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { loadCookieConsent, saveCookieConsent, type CookieConsent } from "@/lib/cookie-consent";

type CookieConsentContextType = {
  consent: CookieConsent | null;
  openSettings: () => void;
};

const CookieConsentContext = createContext<CookieConsentContextType | null>(null);

export function CookieConsentProvider({ children }: { children: ReactNode }) {
  const [consent, setConsent] = useState<CookieConsent | null>(null);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [analyticsChoice, setAnalyticsChoice] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const existing = loadCookieConsent();
    setConsent(existing);
    setOpen(!existing);
    setHydrated(true);
  }, []);

  function acceptAll() {
    setConsent(saveCookieConsent(true));
    setOpen(false);
    setExpanded(false);
  }

  function acceptNecessaryOnly() {
    setConsent(saveCookieConsent(false));
    setOpen(false);
    setExpanded(false);
  }

  function saveSettings() {
    setConsent(saveCookieConsent(analyticsChoice));
    setOpen(false);
    setExpanded(false);
  }

  function openSettings() {
    setAnalyticsChoice(consent?.analytics ?? false);
    setExpanded(false);
    setOpen(true);
  }

  return (
    <CookieConsentContext.Provider value={{ consent, openSettings }}>
      {children}
      {hydrated && open && (
        <div className="fixed inset-x-0 bottom-0 z-50 flex justify-center px-4 pb-4">
          <div className="glass-card w-full max-w-2xl space-y-3 rounded-2xl p-5 shadow-[0_18px_45px_rgba(0,0,0,0.4)]">
            <p className="text-sm text-slate-200">
              Używamy plików cookies niezbędnych do działania serwisu oraz — za Twoją zgodą —
              cookies analitycznych. Szczegóły znajdziesz w{" "}
              <a href="/polityka-prywatnosci" className="text-emerald-300 underline">
                Polityce prywatności
              </a>
              .
            </p>

            {expanded && (
              <div className="rounded-xl border border-border/60 bg-slate-950/40 p-3 text-sm">
                <div className="flex items-center justify-between py-1.5">
                  <span className="text-slate-300">Niezbędne — zawsze włączone</span>
                  <input type="checkbox" checked disabled className="h-4 w-4 accent-emerald-500 opacity-60" />
                </div>
                <div className="flex items-center justify-between py-1.5">
                  <span className="text-slate-300">Analityczne</span>
                  <input
                    type="checkbox"
                    checked={analyticsChoice}
                    onChange={(e) => setAnalyticsChoice(e.target.checked)}
                    className="h-4 w-4 cursor-pointer accent-emerald-500"
                  />
                </div>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              <button
                onClick={acceptAll}
                className="rounded-full bg-emerald-500 px-4 py-2 text-xs font-medium text-slate-950 transition hover:bg-emerald-400"
              >
                Akceptuję wszystkie
              </button>
              <button
                onClick={acceptNecessaryOnly}
                className="rounded-full border border-border/70 px-4 py-2 text-xs font-medium text-slate-200 transition hover:border-slate-500"
              >
                Tylko niezbędne
              </button>
              {expanded ? (
                <button
                  onClick={saveSettings}
                  className="rounded-full border border-emerald-400/60 px-4 py-2 text-xs font-medium text-emerald-200 transition hover:bg-emerald-500/10"
                >
                  Zapisz ustawienia
                </button>
              ) : (
                <button
                  onClick={() => setExpanded(true)}
                  className="rounded-full border border-border/70 px-4 py-2 text-xs font-medium text-slate-200 transition hover:border-slate-500"
                >
                  Ustawienia
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </CookieConsentContext.Provider>
  );
}

export function useCookieConsent() {
  const ctx = useContext(CookieConsentContext);
  if (!ctx) throw new Error("useCookieConsent must be used inside CookieConsentProvider");
  return ctx;
}
