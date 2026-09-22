"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { PhotoRequirementsCard } from "./photo-requirements-card";
import { MultiImageUploader } from "./multi-image-uploader";
import { ReportType, ReportTypeSelector } from "./report-type-selector";
import { SubmitSummaryCard } from "./submit-summary-card";
import { createCase, getCase, getCredits, authMe } from "@/lib/api";
import { REGULAMIN_VERSION, PRIVACY_VERSION } from "@/lib/legal-versions";
import { setPendingSubmission } from "@/lib/submission-store";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/auth-provider";

type InputMode = "photos" | "url";

function pluralAnalyses(n: number): string {
  if (n === 1) return "1 dostępną analizę";
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return `${n} dostępne analizy`;
  return `${n} dostępnych analiz`;
}

export function AnalyzeForm() {
  const { user } = useAuth();
  const [inputMode, setInputMode] = useState<InputMode>("photos");
  const [files, setFiles] = useState<File[]>([]);
  const [auctionUrl, setAuctionUrl] = useState("");
  const [reportType, setReportType] = useState<ReportType>("expert");
  const [email, setEmail] = useState("");
  const [context, setContext] = useState("");
  const [acceptedDisclaimer, setAcceptedDisclaimer] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitPhase, setSubmitPhase] = useState<"idle" | "creating" | "uploading" | "navigating">("idle");
  const [credits, setCredits] = useState<number | null>(null);
  // Regulamin już zaakceptowany w aktualnej wersji przy rejestracji — checkbox
  // przy analizie jest wtedy zbędnym powtórzeniem tego samego kroku. Domyślnie
  // true (wymagany), dopóki nie potwierdzimy inaczej z /auth/me.
  const [regulaminCheckboxNeeded, setRegulaminCheckboxNeeded] = useState(true);
  const router = useRouter();
  // Case_id z poprzedniej nieudanej próby (np. upload zdjęć się urwał) — przy
  // ponowieniu wznawiamy TEN SAM case zamiast tworzyć nowy przy każdym kliknięciu
  // "Analizuj". Bez tego seria nieudanych prób zostawia stertę osieroconych
  // case'ów ze statusem CREATED i zero zdjęć (patrz analiza produkcyjna 2026-09-22).
  const retryCaseIdRef = useRef<string | null>(null);
  // Za co dokładnie odpowiadał retryCaseIdRef (jakie zdjęcia/tryb) — jeśli user
  // między próbami podmienił zdjęcia albo przełączył photos↔url, wznowienie
  // starego case'a wysłałoby analizę na nieaktualnych danych po cichu (code
  // review + QA, 2026-09-22). Mismatch = wymuś nowy case.
  const retryInputSignatureRef = useRef<string | null>(null);

  useEffect(() => {
    if (user?.email) setEmail(user.email);
  }, [user]);

  useEffect(() => {
    if (!user) {
      setCredits(null);
      // Gość i tak zostanie poproszony o zalogowanie/założenie konta zanim
      // run-decision faktycznie ruszy (wymaga auth) — a formularz rejestracji
      // ma ten sam checkbox Regulaminu. Nie dublujemy go tutaj.
      setRegulaminCheckboxNeeded(false);
      setAcceptedDisclaimer(true);
      return;
    }
    getCredits()
      .then((res) => setCredits(res.credits))
      .catch(() => setCredits(null));
    authMe()
      .then((res) => {
        const upToDate = res.regulamin_version === REGULAMIN_VERSION;
        setRegulaminCheckboxNeeded(!upToDate);
        if (upToDate) setAcceptedDisclaimer(true);
      })
      .catch(() => setRegulaminCheckboxNeeded(true));
  }, [user]);

  const minImages = 7;

  // Walidacja URL aukcji
  const isValidAuctionUrl = (url: string) => {
    if (!url.trim()) return false;
    const lower = url.toLowerCase();
    return (
      lower.includes("vinted") ||
      lower.includes("ebay") ||
      lower.includes("kleinanzeigen")
    );
  };

  const canSubmit =
    acceptedDisclaimer &&
    !submitting &&
    (inputMode === "photos"
      ? files.length >= minImages
      : isValidAuctionUrl(auctionUrl));

  async function handleSubmit() {
    setError(null);

    if (!canSubmit) {
      if (inputMode === "photos") {
        setError("Upewnij się, że dodałeś minimum 7 zdjęć i zaakceptowałeś zastrzeżenia.");
      } else {
        setError("Upewnij się, że wkleiłeś prawidłowy link (Vinted, eBay lub Kleinanzeigen) i zaakceptowałeś zastrzeżenia.");
      }
      return;
    }

    // Sygnatura tego, co user faktycznie chce teraz wysłać — jeśli różni się od
    // tego, dla czego założono retryCaseIdRef (podmienił zdjęcia, przełączył
    // photos↔url, poprawił literówkę w emailu / kontekście — email/context są
    // wysyłane TYLKO przy tworzeniu case'a, więc zmiana bez nowego case'a
    // zostałaby po cichu zignorowana, code review 2026-09-22), stary case jest
    // nieaktualny i nie wolno go wznawiać.
    const inputSignature =
      (inputMode === "url"
        ? `url:${auctionUrl}`
        : `photos:${files.map((f) => `${f.name}:${f.size}`).join(",")}`) +
      `|email:${email}|context:${context}`;
    if (retryInputSignatureRef.current !== inputSignature) {
      retryCaseIdRef.current = null;
    }

    try {
      setSubmitting(true);

      // Ponowienie po wcześniejszym błędzie (ten sam input co poprzednio): wznów
      // TEN SAM case zamiast zakładać nowy. Jeśli poprzednia próba faktycznie
      // dotarła do serwera (zdjęcia się zapisały, tylko odpowiedź nie doszła do
      // przeglądarki), pomiń re-upload całkowicie — inaczej te same zdjęcia
      // zostałyby dopisane drugi raz (backend .extend() na liście assets, nie
      // nadpisuje).
      let case_id: string;
      let assetsAlreadySaved = false;
      if (retryCaseIdRef.current) {
        case_id = retryCaseIdRef.current;
        setSubmitPhase("uploading");
        try {
          const existing = (await getCase(case_id, 20_000)) as { assets?: unknown[] };
          assetsAlreadySaved = Array.isArray(existing?.assets) && existing.assets.length > 0;
        } catch {
          // Nie udało się zweryfikować stanu starego case'a — NIE zgadujemy i
          // NIE ponawiamy ślepo na tym samym case_id: dla trybu URL backend
          // twardo odrzuca powtórny import gdy case ma już zdjęcia (400 "Case
          // ma już dodane zdjęcia"), a to zapętliłoby usera bez wyjścia z UI
          // (case_id zostałby, sygnatura inputu ta sama → kolejne kliknięcia
          // trafiałyby w ten sam błąd); dla trybu photos backend .extend()-uje
          // bez limitu, więc powtarzane błędy weryfikacji mogłyby narastająco
          // zdublować zdjęcia ponad liczbę, na jaką skalibrowany jest timeout
          // Agent A (do 12 zdjęć, patrz agent_a_gemini.py). Bezpieczniejszy
          // kompromis: załóż nowy case — rzadki osierocony CREATED case (tylko
          // gdy akurat TA weryfikacja też akurat padnie) jest dużo tańszy niż
          // pętla bez wyjścia albo narastające duplikaty (code review, drugi
          // przegląd, 2026-09-22).
          const created = await createCase(email, undefined, context, {
            regulaminAccepted: acceptedDisclaimer,
            regulaminVersion: REGULAMIN_VERSION,
            privacyVersion: PRIVACY_VERSION,
          });
          case_id = created.case_id;
          retryCaseIdRef.current = case_id;
          retryInputSignatureRef.current = inputSignature;
          assetsAlreadySaved = false;
        }
      } else {
        setSubmitPhase("creating");
        const created = await createCase(email, undefined, context, {
          regulaminAccepted: acceptedDisclaimer,
          regulaminVersion: REGULAMIN_VERSION,
          privacyVersion: PRIVACY_VERSION,
        });
        case_id = created.case_id;
        retryCaseIdRef.current = case_id;
        retryInputSignatureRef.current = inputSignature;
      }

      setSubmitPhase("uploading");
      if (!assetsAlreadySaved) {
        if (inputMode === "url" && auctionUrl) {
          const { importFromUrl } = await import("@/lib/api");
          await importFromUrl(case_id, auctionUrl);
        } else if (inputMode === "photos" && files.length > 0) {
          const { uploadAssets } = await import("@/lib/api");
          const fileData = await Promise.all(
            files.map((f) => new Promise<{ name: string; type: string; buffer: ArrayBuffer }>((resolve, reject) => {
              const reader = new FileReader();
              reader.onload = (e) => resolve({ name: f.name, type: f.type || "image/jpeg", buffer: e.target!.result as ArrayBuffer });
              reader.onerror = reject;
              reader.readAsArrayBuffer(f);
            }))
          );
          const uploadFiles = fileData.map(({ name, type, buffer }) => new File([buffer], name, { type }));
          await uploadAssets(case_id, uploadFiles);
        }
      }

      setSubmitPhase("navigating");
      retryCaseIdRef.current = null;
      retryInputSignatureRef.current = null;
      setPendingSubmission({
        caseId: case_id,
        mode: reportType,
        inputType: inputMode,
        auctionUrl: inputMode === "url" ? auctionUrl : undefined,
      });

      const qs = new URLSearchParams();
      qs.set("case_id", case_id);
      qs.set("mode", reportType);
      router.push(`/analyze/status?${qs.toString()}`);
    } catch (e: any) {
      setError(
        e instanceof Error
          ? e.message
          : "Nie udało się wysłać zgłoszenia. Spróbuj ponownie później."
      );
      setSubmitting(false);
      setSubmitPhase("idle");
    }
  }

  return (
    <div className="grid gap-6 md:grid-cols-[minmax(0,2.1fr),minmax(0,1.1fr)]">
      <div className="min-w-0 space-y-4">
        {/* HERO / PAGE HEADER */}
        <section className="space-y-4">
          <h1 className="text-xl font-semibold tracking-tight text-slate-50 md:text-2xl">
            Prześlij zdjęcia koszulki albo podaj link do aukcji
          </h1>
          <p className="max-w-xl text-sm text-muted-foreground">
            LegitScore analizuje koszulki piłkarskie i generuje szczegółowy
            raport ryzyka autentyczności na podstawie przesłanych zdjęć lub
            linków do ofert marketplace.
          </p>
          {user && credits !== null && credits > 0 && (
            <div className="inline-flex items-center gap-2 rounded-xl border border-emerald-400/40 bg-emerald-500/10 px-4 py-2 shadow-sm shadow-emerald-500/10">
              <Sparkles className="h-4 w-4 shrink-0 text-emerald-300" />
              <span className="text-sm font-semibold text-emerald-200">
                Masz {pluralAnalyses(credits)}
              </span>
            </div>
          )}
          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-3 py-1 font-medium text-emerald-200">
              BETA
            </span>
            {!user && (
              <span className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-3 py-1 font-medium text-emerald-200">
                Pierwsza analiza gratis po założeniu konta
              </span>
            )}
            <span className="rounded-full border border-border/70 bg-slate-950/60 px-3 py-1 text-slate-200">
              Raport ryzyka, nie gwarancja
            </span>
          </div>
        </section>

        {/* STEP 1 — INPUT MODE SELECTOR */}
        <section className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <span className="flex h-6 w-6 items-center justify-center rounded-full border border-emerald-400/60 bg-emerald-500/10 text-[11px] text-emerald-200">
              1
            </span>
            <span>Jak chcesz przeanalizować koszulkę?</span>
          </div>
          <div className="rounded-2xl shadow-[0_18px_45px_rgba(16,185,129,0.25)]">
          <div className="overflow-hidden rounded-2xl border border-emerald-500/20 bg-slate-900/70 p-5 backdrop-blur space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:gap-4">
              <label
                className={`flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 transition ${
                  inputMode === "photos"
                    ? "border-emerald-400/60 bg-emerald-500/10"
                    : "border-border/70 bg-slate-950/40 hover:border-slate-500"
                }`}
              >
                <input
                  type="radio"
                  name="inputMode"
                  value="photos"
                  checked={inputMode === "photos"}
                  onChange={() => setInputMode("photos")}
                  className="h-4 w-4 accent-emerald-500"
                />
                <div>
                  <div className="text-sm font-medium text-slate-100">Dodaj zdjęcia</div>
                  <div className="text-xs text-muted-foreground">Prześlij własne zdjęcia koszulki</div>
                </div>
              </label>
              <label
                className={`flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 transition ${
                  inputMode === "url"
                    ? "border-emerald-400/60 bg-emerald-500/10"
                    : "border-border/70 bg-slate-950/40 hover:border-slate-500"
                }`}
              >
                <input
                  type="radio"
                  name="inputMode"
                  value="url"
                  checked={inputMode === "url"}
                  onChange={() => setInputMode("url")}
                  className="h-4 w-4 accent-emerald-500"
                />
                <div>
                  <div className="text-sm font-medium text-slate-100">Wklej link do aukcji</div>
                  <div className="text-xs text-muted-foreground">Vinted, eBay, Kleinanzeigen</div>
                </div>
              </label>
            </div>

            {/* PHOTOS MODE */}
            {inputMode === "photos" && (
              <div className="space-y-3">
                <div className="rounded-xl border border-amber-400/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-200/80">
                  <span className="font-medium">Wskazówka:</span> Ostre zdjęcia z dobrym oświetleniem znacząco
                  poprawiają dokładność analizy. Prześlij 7–12 zdjęć z różnych kątów.
                </div>
                <MultiImageUploader
                  files={files}
                  onChange={setFiles}
                  minCount={minImages}
                />
              </div>
            )}

            {/* URL MODE */}
            {inputMode === "url" && (
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  <span className="rounded-full border border-violet-400/40 bg-violet-500/10 px-2.5 py-0.5 text-[11px] font-medium text-violet-300">Vinted</span>
                  <span className="rounded-full border border-blue-400/40 bg-blue-500/10 px-2.5 py-0.5 text-[11px] font-medium text-blue-300">eBay</span>
                  <span className="rounded-full border border-red-400/40 bg-red-500/10 px-2.5 py-0.5 text-[11px] font-medium text-red-300">Kleinanzeigen</span>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">
                    Link do oferty
                  </label>
                  <input
                    type="url"
                    value={auctionUrl}
                    onChange={(e) => setAuctionUrl(e.target.value)}
                    className="mt-1 w-full rounded-xl border border-border/70 bg-slate-950/40 px-3 py-2 text-sm outline-none ring-emerald-500/40 placeholder:text-slate-500 focus:ring"
                    placeholder="https://www.vinted.pl/items/... lub https://www.kleinanzeigen.de/s-anzeige/..."
                  />
                </div>
                {auctionUrl && !isValidAuctionUrl(auctionUrl) && (
                  <p className="text-xs text-amber-300">
                    Link musi prowadzić do Vinted, eBay lub Kleinanzeigen.
                  </p>
                )}
                <section className="rounded-2xl border border-emerald-500/20 bg-slate-900/60 p-4 text-xs text-muted-foreground">
                  <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-emerald-200">
                    Jakie zdjęcia powinno zawierać ogłoszenie?
                  </h3>
                  <ul className="space-y-1">
                    {[
                      "przód koszulki",
                      "tył koszulki",
                      "metka wewnętrzna",
                      "herb / emblemat",
                      "logo producenta",
                      "numer lub nazwisko",
                      "szew / kołnierz",
                    ].map((item) => (
                      <li key={item} className="flex items-center gap-2">
                        <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500/15 text-[11px] text-emerald-300">
                          ✓
                        </span>
                        <span className="text-xs text-slate-100">{item}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              </div>
            )}
          </div>
          </div>
          {inputMode === "photos" && <PhotoRequirementsCard />}
        </section>

        {/* STEP 2 — REPORT TYPE */}
        <section className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <span className="flex h-6 w-6 items-center justify-center rounded-full border border-emerald-400/60 bg-emerald-500/10 text-[11px] text-emerald-200">
              2
            </span>
            <span>Wybierz typ raportu</span>
          </div>
          <ReportTypeSelector value={reportType} onChange={setReportType} />
        </section>

        {/* STEP 3 — CONTACT */}
        <section className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <span className="flex h-6 w-6 items-center justify-center rounded-full border border-emerald-400/60 bg-emerald-500/10 text-[11px] text-emerald-200">
              3
            </span>
            <span>Dodaj kontekst (opcjonalnie)</span>
          </div>
          <div className="rounded-2xl shadow-[0_18px_45px_rgba(16,185,129,0.25)]">
          <div className="overflow-hidden rounded-2xl border border-emerald-500/20 bg-slate-900/70 p-5 backdrop-blur space-y-3">
            {user ? (
              <p className="text-xs text-slate-400">
                Jesteś zalogowany jako{" "}
                <span className="font-medium text-emerald-300">{user.email}</span>.
              </p>
            ) : (
              <p className="text-xs text-slate-400">
                Przed uruchomieniem analizy poprosimy Cię o zalogowanie się lub
                założenie darmowego konta — nie musisz podawać adresu email tutaj.
              </p>
            )}
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">
                Dodatkowy kontekst / opis (opcjonalnie)
              </label>
              <textarea
                value={context}
                onChange={(e) => setContext(e.target.value)}
                className="min-h-[90px] w-full rounded-xl border border-border/70 bg-slate-950/40 px-3 py-2 text-sm outline-none ring-emerald-500/40 placeholder:text-slate-500 focus:ring"
                placeholder="Np. źródło koszulki, podejrzenia, szczegóły meczu, historia przedmiotu..."
              />
            </div>
          </div>
          </div>
        </section>

        {error && (
          <p className="text-xs text-amber-300" role="alert">
            {error}
          </p>
        )}
      </div>

      {/* SUMMARY / CTA */}
      <SubmitSummaryCard
        reportType={reportType}
        inputMode={inputMode}
        imageCount={files.length}
        minImages={minImages}
        auctionUrl={auctionUrl}
        isValidUrl={isValidAuctionUrl(auctionUrl)}
        email={email}
        canSubmit={canSubmit}
        onSubmit={handleSubmit}
        submitting={submitting}
        submitPhase={submitPhase}
        isLoggedIn={Boolean(user)}
        credits={credits}
        disclaimerAccepted={acceptedDisclaimer}
        onDisclaimerChange={setAcceptedDisclaimer}
        showDisclaimerCheckbox={regulaminCheckboxNeeded}
      />
    </div>
  );
}


