"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/auth-provider";
import {
  getPricing,
  getCredits,
  createCheckout,
  redeemPromoCode,
  type BillingPackage,
  type BillingPackageKey,
} from "@/lib/api";
import { Loader2, Sparkles, Ticket } from "lucide-react";
import { LuckyCodeBanner } from "@/components/billing/lucky-code-banner";

function formatPrice(grosz: number): string {
  return `${(grosz / 100).toFixed(2).replace(".00", "")} zł`;
}

const PACKAGE_ORDER: BillingPackageKey[] = ["single", "pack3", "pack10"];

export default function BillingPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [packages, setPackages] = useState<Record<BillingPackageKey, BillingPackage> | null>(null);
  const [credits, setCredits] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [buyingPackage, setBuyingPackage] = useState<BillingPackageKey | null>(null);

  const [promoCode, setPromoCode] = useState("");
  const [promoMessage, setPromoMessage] = useState<string | null>(null);
  const [promoError, setPromoError] = useState<string | null>(null);
  const [redeemingPromo, setRedeemingPromo] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login?next=/billing");
      return;
    }
    Promise.all([getPricing(), getCredits()])
      .then(([pricing, creditsRes]) => {
        setPackages(pricing.packages);
        setCredits(creditsRes.credits);
      })
      .catch((err: any) => setError(err.message || "Nie udało się pobrać cennika."));
  }, [user, authLoading, router]);

  async function handleBuy(pkg: BillingPackageKey) {
    setError(null);
    setBuyingPackage(pkg);
    try {
      const { checkout_url } = await createCheckout(pkg);
      window.location.href = checkout_url;
    } catch (err: any) {
      setError(err.message || "Nie udało się utworzyć płatności. Spróbuj ponownie.");
      setBuyingPackage(null);
    }
  }

  async function handleRedeemPromo() {
    if (!promoCode.trim()) return;
    setPromoMessage(null);
    setPromoError(null);
    setRedeemingPromo(true);
    try {
      const res = await redeemPromoCode(promoCode.trim());
      setPromoMessage(res.message);
      setCredits(res.credits);
      setPromoCode("");
    } catch (err: any) {
      setPromoError(err.message || "Nie udało się wykorzystać kodu.");
    } finally {
      setRedeemingPromo(false);
    }
  }

  if (authLoading || (!user && !error)) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-5 py-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-50">Kup analizy</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {credits !== null
            ? `Dostępne kredyty: ${credits}`
            : "Pierwsza analiza jest zawsze darmowa — kolejne kupujesz pojedynczo albo w pakiecie."}
        </p>
      </div>

      <LuckyCodeBanner onRedeemed={setCredits} />

      {error && (
        <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>
      )}

      {packages === null && !error && (
        <div className="flex flex-1 items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-emerald-400" />
        </div>
      )}

      {packages !== null && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {PACKAGE_ORDER.map((key) => {
            const pkg = packages[key];
            if (!pkg) return null;
            const perUnit = pkg.credits > 1 ? pkg.price_pln_grosz / pkg.credits : null;
            const isBuying = buyingPackage === key;
            return (
              <div
                key={key}
                className="glass-card flex flex-col gap-3 p-5 text-center"
              >
                <Sparkles className="mx-auto h-5 w-5 text-emerald-400" />
                <div>
                  <p className="text-sm font-medium text-slate-200">{pkg.label}</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-50">
                    {formatPrice(pkg.price_pln_grosz)}
                  </p>
                  {perUnit !== null && (
                    <p className="text-[11px] text-muted-foreground">
                      {formatPrice(perUnit)} / analiza
                    </p>
                  )}
                </div>
                <button
                  onClick={() => handleBuy(key)}
                  disabled={buyingPackage !== null}
                  className="mt-auto inline-flex items-center justify-center gap-1.5 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-400 disabled:opacity-60"
                >
                  {isBuying ? <Loader2 className="h-4 w-4 animate-spin" /> : "Kup"}
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className="glass-card flex flex-col gap-3 p-5">
        <div className="flex items-center gap-2">
          <Ticket className="h-4 w-4 text-emerald-400" />
          <p className="text-sm font-medium text-slate-200">Masz kod zaproszenia?</p>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={promoCode}
            onChange={(e) => setPromoCode(e.target.value)}
            placeholder="Wpisz kod"
            className="flex-1 rounded-lg border border-border/60 bg-slate-900/60 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:border-emerald-400/60 focus:outline-none"
          />
          <button
            onClick={handleRedeemPromo}
            disabled={redeemingPromo || !promoCode.trim()}
            className="rounded-lg border border-emerald-400/40 px-4 py-2 text-sm font-medium text-emerald-300 transition hover:bg-emerald-400/10 disabled:opacity-60"
          >
            {redeemingPromo ? <Loader2 className="h-4 w-4 animate-spin" /> : "Wykorzystaj"}
          </button>
        </div>
        {promoMessage && <p className="text-xs text-emerald-300">{promoMessage}</p>}
        {promoError && <p className="text-xs text-red-300">{promoError}</p>}
      </div>
    </div>
  );
}
