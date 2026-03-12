"use client";

import { useState } from "react";
import { PhotoRequirementsCard } from "./photo-requirements-card";
import { MultiImageUploader } from "./multi-image-uploader";
import { ReportType, ReportTypeSelector } from "./report-type-selector";
import { SubmissionDisclaimer } from "./submission-disclaimer";
import { SubmitSummaryCard } from "./submit-summary-card";
import { createCase } from "@/lib/api";
import { setPendingSubmission } from "@/lib/submission-store";
import { useRouter } from "next/navigation";

export function AnalyzeForm() {
  const [files, setFiles] = useState<File[]>([]);
  const [reportType, setReportType] = useState<ReportType>("basic");
  const [email, setEmail] = useState("");
  const [offerLink, setOfferLink] = useState("");
  const [context, setContext] = useState("");
  const [acceptedDisclaimer, setAcceptedDisclaimer] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  const minImages = 7;
  const canSubmit =
    files.length >= minImages &&
    acceptedDisclaimer &&
    email.trim().length > 0 &&
    !submitting;

  async function handleSubmit() {
    setError(null);

    if (!canSubmit) {
      setError(
        "Upewnij się, że dodałeś minimum 7 zdjęć, podałeś email i zaakceptowałeś zastrzeżenia."
      );
      return;
    }

    try {
      setSubmitting(true);
      // 1) Tworzymy sprawę z emailem, linkiem do oferty i kontekstem
      const { case_id } = await createCase(email, offerLink, context);
      // 2) Zapisujemy dane lokalne do dalszego przetwarzania na ekranie statusu.
      setPendingSubmission({
        caseId: case_id,
        mode: reportType,
        files,
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
            Oceń autentyczność koszulki piłkarskiej
          </h1>
          <p className="max-w-xl text-sm text-muted-foreground">
            Prześlij zdjęcia koszulki, a LegitScore przygotuje raport ryzyka
            autentyczności.
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

        {/* STEP 1 — PHOTOS */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
              <span className="flex h-6 w-6 items-center justify-center rounded-full border border-emerald-400/60 bg-emerald-500/10 text-[11px] text-emerald-200">
                1
              </span>
              <span>Dodaj zdjęcia koszulki</span>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Im lepsza jakość i kompletność zdjęć, tym bardziej wiarygodny raport.
          </p>
          <section className="rounded-2xl border border-emerald-500/20 bg-slate-900/70 p-5 shadow-[0_18px_45px_rgba(16,185,129,0.25)] backdrop-blur">
            <p className="mb-3 text-xs text-muted-foreground">
              Dodaj 7–12 zdjęć koszulki. Lepsza jakość i kompletność zdjęć = bardziej
              wiarygodny raport.
            </p>
            <MultiImageUploader
              files={files}
              onChange={setFiles}
              minCount={minImages}
            />
          </section>
          <PhotoRequirementsCard />
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
            <span>Podaj dane kontaktowe i kontekst</span>
          </div>
          <div className="rounded-2xl border border-emerald-500/20 bg-slate-900/70 p-5 shadow-[0_18px_45px_rgba(16,185,129,0.25)] backdrop-blur space-y-3">
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
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">
                Link do oferty lub cena zakupu (opcjonalnie)
              </label>
              <input
                type="text"
                value={offerLink}
                onChange={(e) => setOfferLink(e.target.value)}
                className="w-full rounded-xl border border-border/70 bg-slate-950/40 px-3 py-2 text-sm outline-none ring-emerald-500/40 placeholder:text-slate-500 focus:ring"
                placeholder="np. link do aukcji, cena w zł"
              />
            </div>
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
        imageCount={files.length}
        minImages={minImages}
        email={email}
        canSubmit={canSubmit}
        onSubmit={handleSubmit}
        submitting={submitting}
      />
    </div>
  );
}


