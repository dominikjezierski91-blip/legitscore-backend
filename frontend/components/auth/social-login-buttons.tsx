"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/auth/auth-provider";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
const FACEBOOK_APP_ID = process.env.NEXT_PUBLIC_FACEBOOK_APP_ID;

type Consent = { regulaminVersion: string; privacyVersion: string };

function loadScriptOnce(src: string, id: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.getElementById(id)) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.defer = true;
    script.id = id;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Nie udało się załadować ${src}`));
    document.body.appendChild(script);
  });
}

/**
 * Przyciski "Kontynuuj przez Google/Facebook". Renderują się tylko gdy front ma
 * skonfigurowane NEXT_PUBLIC_GOOGLE_CLIENT_ID / NEXT_PUBLIC_FACEBOOK_APP_ID — dopóki
 * Dominik nie założy aplikacji w Google Cloud Console / Meta for Developers, komponent
 * po prostu nic nie renderuje (nie psuje strony logowania/rejestracji).
 *
 * `consentAccepted` gate'uje UŻYWALNOŚĆ przycisków (backend i tak wymaga zgody tylko
 * przy zakładaniu NOWEGO konta, ale front prosi o nią z góry dla obu dostawców, żeby
 * user nie trafił na 400 dopiero po wybraniu Google/Facebook).
 */
export function SocialLoginButtons({
  consentAccepted,
  consent,
  onError,
}: {
  consentAccepted: boolean;
  consent?: Consent;
  onError: (message: string) => void;
}) {
  const { loginWithGoogle, loginWithFacebook } = useAuth();
  const googleButtonRef = useRef<HTMLDivElement>(null);
  const [fbReady, setFbReady] = useState(false);
  const [fbLoading, setFbLoading] = useState(false);

  // Google Identity Services trzyma callback z inicjalizacji na stałe (renderButton
  // się nie odświeża) — najnowszy stan zgody czytamy z refa, żeby nie musieć
  // re-inicjalizować (i duplikować) przycisku przy każdej zmianie checkboxa.
  const latestRef = useRef({ consentAccepted, consent });
  useEffect(() => {
    latestRef.current = { consentAccepted, consent };
  }, [consentAccepted, consent]);

  const handleGoogleCredential = useCallback(
    async (response: { credential: string }) => {
      const { consentAccepted: accepted, consent: c } = latestRef.current;
      if (!accepted) {
        onError("Zaznacz zgodę na Regulamin i Politykę prywatności, żeby się zalogować.");
        return;
      }
      try {
        await loginWithGoogle(response.credential, c);
      } catch (err: any) {
        onError(err.message || "Błąd logowania przez Google.");
      }
    },
    [loginWithGoogle, onError]
  );

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    let cancelled = false;
    loadScriptOnce("https://accounts.google.com/gsi/client", "google-identity-script")
      .then(() => {
        if (cancelled) return;
        const google = (window as any).google;
        google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: handleGoogleCredential,
        });
        if (googleButtonRef.current) {
          google.accounts.id.renderButton(googleButtonRef.current, {
            theme: "outline",
            size: "large",
            width: 320,
            text: "continue_with",
            shape: "pill",
            locale: "pl",
          });
        }
      })
      .catch(() => onError("Nie udało się załadować logowania Google."));
    return () => {
      cancelled = true;
    };
  }, [handleGoogleCredential, onError]);

  useEffect(() => {
    if (!FACEBOOK_APP_ID) return;
    let cancelled = false;
    loadScriptOnce("https://connect.facebook.net/pl_PL/sdk.js", "facebook-jssdk")
      .then(() => {
        if (cancelled) return;
        (window as any).FB.init({
          appId: FACEBOOK_APP_ID,
          cookie: true,
          xfbml: false,
          version: "v21.0",
        });
        setFbReady(true);
      })
      .catch(() => onError("Nie udało się załadować logowania Facebook."));
    return () => {
      cancelled = true;
    };
  }, [onError]);

  const handleFacebookClick = () => {
    if (!consentAccepted) {
      onError("Zaznacz zgodę na Regulamin i Politykę prywatności, żeby się zalogować.");
      return;
    }
    const FB = (window as any).FB;
    if (!FB) return;
    setFbLoading(true);
    FB.login(
      (resp: any) => {
        setFbLoading(false);
        if (resp?.authResponse?.accessToken) {
          loginWithFacebook(resp.authResponse.accessToken, consent).catch((err: any) => {
            onError(err.message || "Błąd logowania przez Facebook.");
          });
        }
      },
      { scope: "email", auth_type: "rerequest" }
    );
  };

  if (!GOOGLE_CLIENT_ID && !FACEBOOK_APP_ID) return null;

  return (
    <div className="space-y-2">
      {GOOGLE_CLIENT_ID && (
        <div
          className={
            "flex justify-center transition [&>div]:!w-full " +
            (consentAccepted ? "" : "pointer-events-none opacity-50")
          }
        >
          <div ref={googleButtonRef} />
        </div>
      )}
      {FACEBOOK_APP_ID && (
        <button
          type="button"
          onClick={handleFacebookClick}
          disabled={fbLoading || !fbReady || !consentAccepted}
          className="flex w-full items-center justify-center gap-2 rounded-full border border-border/60 bg-slate-900/60 px-4 py-2.5 text-sm font-medium text-slate-100 transition hover:bg-slate-800/60 disabled:opacity-50"
        >
          {fbLoading ? "Łączenie z Facebookiem..." : "Kontynuuj przez Facebook"}
        </button>
      )}
    </div>
  );
}
