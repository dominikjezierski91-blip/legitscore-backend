"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth/auth-provider";
import { getLuckyCodeStatus, redeemPromoCode } from "@/lib/api";
import { Gift, Loader2 } from "lucide-react";

type Props = {
  onRedeemed?: (credits: number) => void;
};

export function LuckyCodeBanner({ onRedeemed }: Props) {
  const { user } = useAuth();
  const [status, setStatus] = useState<{ code: string; credits: number; available: boolean } | null>(null);
  const [redeeming, setRedeeming] = useState(false);
  const [redeemed, setRedeemed] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      onRedeemed?.(res.credits);
    } catch (err: any) {
      setError(err.message || "Nie udało się odebrać kodu.");
    } finally {
      setRedeeming(false);
    }
  }

  if (!user || !status || !status.available || redeemed) return null;

  return (
    <div className="glass-card flex flex-wrap items-center justify-between gap-3 border-emerald-400/30 p-4">
      <div className="flex items-center gap-2.5">
        <Gift className="h-5 w-5 shrink-0 text-emerald-400" />
        <p className="text-sm text-slate-200">
          Masz kod <span className="font-semibold text-emerald-300">{status.code}</span> na{" "}
          {status.credits} kolejne analizy za darmo.
        </p>
      </div>
      <div className="flex items-center gap-2">
        {error && <p className="text-xs text-red-300">{error}</p>}
        <button
          onClick={handleRedeem}
          disabled={redeeming}
          className="inline-flex items-center justify-center gap-1.5 rounded-full bg-emerald-500 px-4 py-2 text-xs font-semibold text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-400 disabled:opacity-60"
        >
          {redeeming ? <Loader2 className="h-4 w-4 animate-spin" /> : "Odbierz"}
        </button>
      </div>
    </div>
  );
}
