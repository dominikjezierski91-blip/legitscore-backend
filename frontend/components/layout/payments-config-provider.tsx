"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { getConfig } from "@/lib/api";

// SPEC "Darmowe analizy w becie + ukrycie płatności za feature flagą"
// (2026-09-27), §2/§3: jedno źródło prawdy dla płatności — backend. Frontend
// pobiera efektywną wartość z /api/config; NEXT_PUBLIC_PAYMENTS_ENABLED służy
// tylko jako fallback podczas ładowania (zanim odpowiedź backendu dotrze),
// nigdy jako ostateczna decyzja. Nie hardkodować `false` w komponentach —
// wszystkie miejsca mają czytać stąd, przez usePaymentsEnabled().
const ENV_FALLBACK = process.env.NEXT_PUBLIC_PAYMENTS_ENABLED === "true";

type PaymentsConfigContextType = {
  paymentsEnabled: boolean;
  loaded: boolean;
};

const PaymentsConfigContext = createContext<PaymentsConfigContextType>({
  paymentsEnabled: ENV_FALLBACK,
  loaded: false,
});

export function PaymentsConfigProvider({ children }: { children: ReactNode }) {
  const [paymentsEnabled, setPaymentsEnabled] = useState(ENV_FALLBACK);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getConfig()
      .then((cfg) => {
        if (!cancelled) setPaymentsEnabled(cfg.payments_enabled);
      })
      .catch(() => {
        // Backend nieosiągalny — zostań przy fallbacku z env var zamiast
        // rozbijać stronę; /api/config jest lekkie i bezauth, więc porażka
        // tu zwykle oznacza szerszy problem, nie coś specyficznego dla flagi.
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PaymentsConfigContext.Provider value={{ paymentsEnabled, loaded }}>
      {children}
    </PaymentsConfigContext.Provider>
  );
}

// `loaded` celowo pominięte w zwracanej wartości hooka — komponenty mają się
// renderować od razu z fallbackiem (spójne z resztą apki, patrz simPercent w
// analyze-status.tsx), nie migać layoutem po doładowaniu configu.
export function usePaymentsEnabled(): boolean {
  return useContext(PaymentsConfigContext).paymentsEnabled;
}
