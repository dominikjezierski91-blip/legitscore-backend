"use client";

import { useState, useEffect } from "react";
import { PhotoRequirementsCard } from "./photo-requirements-card";
import { MultiImageUploader } from "./multi-image-uploader";
import { ReportType, ReportTypeSelector } from "./report-type-selector";
import { SubmissionDisclaimer } from "./submission-disclaimer";
import { SubmitSummaryCard } from "./submit-summary-card";
import { createCase } from "@/lib/api";
import { setPendingSubmission } from "@/lib/submission-store";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/auth-provider";

type InputMode = "photos" | "url";

export function AnalyzeForm() {
  const { user } = useAuth();
  const [inputMode, setInputMode] = useState<InputMode>("photos");
  const [files, setFiles] = useState<File[]>([]);
  const [auctionUrl, setAuctionUrl] = useState("");
  const [reportType, setReportType] = useState<ReportType>("basic");
  const [email, setEmail] = useState("");
  const [context, setContext] = useState("");
  const [acceptedDisclaimer, setAcceptedDisclaimer] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (user?.email) setEmail(user.email);
  }, [user]);

  const minImages = 7;

  // Walidacja URL aukcji
  const isValidAuctionUrl = (url: string) => {
    if (!url.trim()) return false;
    const lower = url.toLowerCase();
    return (
      lower.includes("vinted") ||
      lower.includes("allegro") ||
      lower.includes("ebay")
    );
  };

  const canSubmit =
    acceptedDisclaimer &&
    email.trim().length > 0 &&
    !submitting &&
    (inputMode === "photos"
      ? files.length >= minImages
      : isValidAuctionUrl(auctionUrl));

  async function handleSubmit() {
    setError(null);

    if (!canSubmit) {
      if (inputMode === "photos") {
        setError(
          user
            ? "Upewnij się, że dodałeś minimum 7 zdjęć i zaakceptowałeś zastrzeżenia."
            : "Upewnij się, że dodałeś minimum 7 zdjęć, podałeś email i zaakceptowałeś zastrzeżenia."
        );
      } else {
        setError(
          user
            ? "Upewnij się, że wkleiłeś prawidłowy link (Vinted, Allegro lub eBay) i zaakceptowałeś zastrzeżenia."
            : "Upewnij się, że wkleiłeś prawidłowy link (Vinted, Allegro lub eBay), podałeś email i zaakceptowałeś zastrzeżenia."
        );
      }
      return;
    }

    try {
      setSubmitting(true);
      // 1) Tworzymy sprawę z emailem i kontekstem
      const { case_id } = await createCase(email, undefined, context);
      // 2) Zapisujemy dane lokalne do dalszego przetwarzania na ekranie statusu.
      setPendingSubmission({
        caseId: case_id,
        mode: reportType,
        inputType: inputMode,
        files: inputMode === "photos" ? files : undefined,
        auctionUrl: inputMode === "url" ? auctionUrl : undefined,
      });
      // 3) Od razu przechodzimy na stronę statusu, gdzie wykonujemy upload + analizę.
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
    }
  }

  return (
    <div className="grid gap-6 md:grid-cols-[minmax(0,2.1fr),minmax(0,1.1fr)]">
      <div className="space-y-4">
        {/* HERO / PAGE HEADER */}
        <section className="space-y-4">
          <h1 className="text-xl font-semibold tracking-tight text-slate-50 md:text-2xl">
            Prześlij zdjęcia koszulki albo podaj link do aukcji
          </h1>
          <p className="max-w-xl text-sm text-muted-foreground">
            LegitScore analizuje koszulki piłkarskie i generuje szczegółowy
            raport ryzyka autentyczności na podstawie przesłanych zdjęć.
          </p>
          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-3 py-1 font-medium text-emerald-200">
              BETA
            </span>
            <span className="rounded-full border border-border/70 bg-slate-950/60 px-3 py-1 text-slate-200">
              Darmowe w becie
            </span>
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
          <div className="rounded-2xl border border-emerald-500/20 bg-slate-900/70 p-5 shadow-[0_18px_45px_rgba(16,185,129,0.25)] backdrop-blur space-y-4">
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
                  <div className="text-xs text-muted-foreground">Vinted, Allegro lub eBay</div>
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
                  <span className="rounded-full border border-orange-400/40 bg-orange-500/10 px-2.5 py-0.5 text-[11px] font-medium text-orange-300">Allegro</span>
                  <span className="rounded-full border border-blue-400/40 bg-blue-500/10 px-2.5 py-0.5 text-[11px] font-medium text-blue-300">eBay</span>
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
                    placeholder="https://www.vinted.pl/items/... lub https://allegro.pl/oferta/..."
                  />
                </div>
                {auctionUrl && !isValidAuctionUrl(auctionUrl) && (
                  <p className="text-xs text-amber-300">
                    Link musi prowadzić do Vinted, Allegro lub eBay.
                  </p>
                )}
                <div className="rounded-xl border border-slate-700/50 bg-slate-900/40 p-3 text-xs text-slate-400 space-y-1.5">
                  <p className="font-medium text-slate-300">Dla najlepszej analizy ogłoszenie powinno zawierać:</p>
                  <ul className="space-y-1">
                    <li className="flex gap-2"><span className="text-emerald-400">·</span> Przód koszulki (pełne zdjęcie)</li>
                    <li className="flex gap-2"><span className="text-emerald-400">·</span> Tył koszulki</li>
                    <li className="flex gap-2"><span className="text-emerald-400">·</span> Zbliżenie herbu lub logo producenta</li>
                    <li className="flex gap-2"><span className="text-slate-500">·</span> Zdjęcie metryczki lub nadruku szyjnego (opcjonalnie)</li>
                  </ul>
                </div>
              </div>
            )}
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
            <span>{user ? "Dodaj kontekst (opcjonalnie)" : "Podaj dane kontaktowe i kontekst"}</span>
          </div>
          <div className="rounded-2xl border border-emerald-500/20 bg-slate-900/70 p-5 shadow-[0_18px_45px_rgba(16,185,129,0.25)] backdrop-blur space-y-3">
            {user ? (
              <p className="text-xs text-slate-400">
                Jesteś zalogowany jako{" "}
                <span className="font-medium text-emerald-300">{user.email}</span>.
              </p>
            ) : (
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">
                  Email (wymagany)
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl border border-border/70 bg-slate-950/40 px-3 py-2 text-sm outline-none ring-emerald-500/40 placeholder:text-slate-500 focus:ring"
                  placeholder="np. twoj.email@example.com"
                />
                <p className="pt-1 text-xs italic text-muted-foreground">
                  Wpisując adres email, zgadzasz się na kontakt w sprawie raportu
                  oraz informacje o rozwoju LegitScore.
                </p>
              </div>
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
        </section>

        {/* STEP 4 — DISCLAIMER / CTA */}
        <section className="mt-4 space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <span className="flex h-6 w-6 items-center justify-center rounded-full border border-emerald-400/60 bg-emerald-500/10 text-[11px] text-emerald-200">
              4
            </span>
            <span>Uruchom analizę</span>
          </div>
          <SubmissionDisclaimer
            accepted={acceptedDisclaimer}
            onChange={setAcceptedDisclaimer}
          />
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
      />
    </div>
  );
}


