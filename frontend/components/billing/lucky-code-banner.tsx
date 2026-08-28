"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "@/components/auth/auth-provider";
import { getLuckyCodeStatus, redeemPromoCode } from "@/lib/api";
import { Gift, Loader2, PartyPopper, X } from "lucide-react";

type Props = {
  onRedeemed?: (credits: number) => void;
};

export function LuckyCodeBanner({ onRedeemed }: Props) {
  const { user } = useAuth();
  const [status, setStatus] = useState<{ code: string; credits: number; available: boolean } | null>(null);
  const [redeeming, setRedeeming] = useState(false);
  const [redeemed, setRedeemed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successCredits, setSuccessCredits] = useState<number | null>(null);

  useEffect(() => {
    if (!user) return;
    getLuckyCodeStatus()
      .then(setStatus)
      .catch(() => {});
  }, [user]);

  async function handleRedeem() {
    if (!status) return;
    setRedeeming(true);
    setError(null);
    try {
      const res = await redeemPromoCode(status.code);
      setRedeemed(true);
      setSuccessCredits(status.credits);
      onRedeemed?.(res.credits);
    } catch (err: any) {
      setError(err.message || "Nie udało się odebrać kodu.");
    } finally {
      setRedeeming(false);
    }
  }

  const showBanner = user && status?.available && !redeemed;

  return (
    <>
      {showBanner && (
        <div className="relative overflow-hidden rounded-2xl border border-emerald-400/40 bg-gradient-to-br from-emerald-500/20 via-emerald-600/10 to-cyan-500/10 p-4 shadow-lg shadow-emerald-500/10 sm:p-5">
          <div className="pointer-events-none absolute -right-8 -top-10 h-32 w-32 rounded-full bg-emerald-400/25 blur-2xl" />
          <div className="pointer-events-none absolute -bottom-8 -left-6 h-24 w-24 rounded-full bg-cyan-400/20 blur-2xl" />

          <div className="relative flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-400/20 ring-1 ring-emerald-400/40">
                <Gift className="h-5 w-5 text-emerald-300" />
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-300">
                  Kod promocyjny
                </p>
                <p className="text-sm font-medium leading-snug text-slate-100">
                  Kod{" "}
                  <span className="rounded-md bg-emerald-500/20 px-1.5 py-0.5 font-mono text-[13px] font-bold tracking-wide text-emerald-200">
                    {status.code}
                  </span>{" "}
                  daje Ci <span className="font-semibold text-emerald-300">{status.credits} kolejne Legity</span> za darmo
                </p>
              </div>
            </div>
            <div className="flex flex-col items-end gap-1">
              <button
                onClick={handleRedeem}
                disabled={redeeming}
                className="inline-flex items-center justify-center gap-1.5 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-slate-950 shadow-md shadow-emerald-500/40 transition hover:bg-emerald-400 disabled:opacity-60"
              >
                {redeeming ? <Loader2 className="h-4 w-4 animate-spin" /> : "Odbierz teraz"}
              </button>
              {error && <p className="text-xs text-red-300">{error}</p>}
            </div>
          </div>
        </div>
      )}

      {successCredits !== null &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
            onClick={() => setSuccessCredits(null)}
          >
            <div
              className="relative w-full max-w-sm space-y-4 rounded-2xl border border-emerald-400/30 bg-slate-950/95 p-6 text-center shadow-2xl shadow-emerald-500/20"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => setSuccessCredits(null)}
                className="absolute right-3 top-3 rounded-full p-1 text-slate-500 transition hover:text-slate-200"
                aria-label="Zamknij"
              >
                <X className="h-4 w-4" />
              </button>
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-400/20 ring-1 ring-emerald-400/40">
                <PartyPopper className="h-7 w-7 text-emerald-300" />
              </div>
              <div>
                <p className="text-lg font-semibold text-slate-50">Kod odebrany!</p>
                <p className="mt-1 text-sm text-slate-300">
                  Dodaliśmy <span className="font-semibold text-emerald-300">{successCredits} Legity</span> do
                  Twojego konta.
                </p>
              </div>
              <button
                onClick={() => setSuccessCredits(null)}
                className="w-full rounded-full bg-emerald-500 py-2.5 text-sm font-semibold text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-400"
              >
                Super, dzięki!
              </button>
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
