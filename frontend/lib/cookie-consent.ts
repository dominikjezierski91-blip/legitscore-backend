const STORAGE_KEY = "legitscore_cookie_consent";

export type CookieConsent = {
  necessary: true;
  analytics: boolean;
  decidedAt: string;
};

export function loadCookieConsent(): CookieConsent | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.analytics === "boolean" && typeof parsed?.decidedAt === "string") {
      return { necessary: true, analytics: parsed.analytics, decidedAt: parsed.decidedAt };
    }
    return null;
  } catch {
    return null;
  }
}

export function saveCookieConsent(analytics: boolean): CookieConsent {
  const consent: CookieConsent = {
    necessary: true,
    analytics,
    decidedAt: new Date().toISOString(),
  };
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(consent));
  }
  return consent;
}

/**
 * Do wywołania przez przyszły kod inicjalizujący GA/PostHog, zanim załaduje
 * jakikolwiek skrypt analityczny — dziś w kodzie nie ma jeszcze takiej integracji.
 */
export function hasAnalyticsConsent(): boolean {
  return loadCookieConsent()?.analytics === true;
}
