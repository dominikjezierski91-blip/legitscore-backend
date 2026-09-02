"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/auth-provider";
import {
  getPricing,
  getBillingSummary,
  createCheckout,
  redeemPromoCode,
  type BillingPackage,
  type BillingPackageKey,
  type BillingSummary,
} from "@/lib/api";
import { Loader2, Sparkles, Ticket, Zap, ShieldCheck, Receipt } from "lucide-react";
import { LuckyCodeBanner } from "@/components/billing/lucky-code-banner";
import { declineAnaliza } from "@/lib/utils";

function formatPrice(grosz: number): string {
  return `${(grosz / 100).toFixed(2).replace(".00", "")} zł`;
}

const PACKAGE_ORDER: BillingPackageKey[] = ["single", "pack3", "pack10"];

// Wizualne wyróżnienie rosnące z wielkością pakietu — złoty akcent na
// "Ekstraklasa" świadomie powtarza ten sam język (ring-amber, gradient
// amber-300→amber-500), którego już używamy dla zweryfikowanej oryginalnej
// koszulki w Kolekcji (isGenuineVerified), żeby "premium" znaczyło to samo
// wizualnie w całej apce.
const PACKAGE_STYLE: Record<BillingPackageKey, {
  ring: string;
  icon: string;
  button: string;
  badge?: string;
  description: string;
}> = {
  single: {
    ring: "",
    icon: "text-slate-400",
    button: "bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/30 hover:bg-emerald-400",
    description: "Taniej niż kawa na mieście — a sprawdza koszulkę wartą setki złotych.",
  },
  pack3: {
    ring: "ring-1 ring-emerald-400/40",
    icon: "text-emerald-400",
    button: "bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/30 hover:bg-emerald-400",
    description: "Dla aktywnych kupujących. ~1,7% ceny koszulki za 500 zł — tyle kosztuje spokój.",
  },
  pack10: {
    ring: "ring-1 ring-amber-400/40",
    icon: "text-amber-400",
    button: "bg-gradient-to-br from-amber-300 to-amber-500 text-amber-950 shadow-md shadow-amber-500/30 hover:from-amber-200 hover:to-amber-400",
    badge: "Najlepsza cena za analizę",
    description: "Ekspert bierze zwykle 50–200 zł za ocenę. U nas 7,90 zł za analizę.",
  },
};

export default function BillingPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [packages, setPackages] = useState<Record<BillingPackageKey, BillingPackage> | null>(null);
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [buyingPackage, setBuyingPackage] = useState<BillingPackageKey | null>(null);

  const [promoCode, setPromoCode] = useState("");
  const [promoMessage, setPromoMessage] = useState<string | null>(null);
  const [promoError, setPromoError] = useState<string | null>(null);
  const [redeemingPromo, setRedeemingPromo] = useState(false);

  const credits = summary?.credits ?? null;

  function refreshSummary() {
    getBillingSummary()
      .then(setSummary)
      .catch(() => {});
  }

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login?next=/billing");
      return;
    }
    Promise.all([getPricing(), getBillingSummary()])
      .then(([pricing, summaryRes]) => {
        setPackages(pricing.packages);
        setSummary(summaryRes);
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
      refreshSummary();
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

  const totalPurchasedCredits = (summary?.purchases ?? []).reduce((sum, p) => sum + p.credits, 0);

  return (
    <div className="flex flex-1 flex-col gap-5 py-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-50">Twoje analizy</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {credits === null
            ? "Pierwsza analiza jest zawsze darmowa — kolejne kupujesz pojedynczo albo w pakiecie."
            : "Przegląd salda, historii analiz i zakupów."}
        </p>
      </div>

      {summary && (
        <div className="grid grid-cols-3 gap-2.5 sm:gap-3">
          <div className="glass-card flex flex-col items-center gap-1 p-4 text-center">
            <Zap className="h-4 w-4 text-emerald-400" />
            <p className="text-2xl font-bold tracking-tight text-emerald-300">{summary.credits}</p>
            <p className="text-[10px] uppercase tracking-wide text-slate-500">Dostępne analizy</p>
          </div>
          <div className="glass-card flex flex-col items-center gap-1 p-4 text-center">
            <ShieldCheck className="h-4 w-4 text-slate-300" />
            <p className="text-2xl font-bold tracking-tight text-slate-100">{summary.analyses_completed}</p>
            <p className="text-[10px] uppercase tracking-wide text-slate-500">Wykonane analizy</p>
          </div>
          <div className="glass-card flex flex-col items-center gap-1 p-4 text-center">
            <Receipt className="h-4 w-4 text-slate-300" />
            <p className="text-2xl font-bold tracking-tight text-slate-100">{totalPurchasedCredits}</p>
            <p className="text-[10px] uppercase tracking-wide text-slate-500">Łącznie kupione analizy</p>
          </div>
        </div>
      )}

      <LuckyCodeBanner onRedeemed={refreshSummary} />

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
            const style = PACKAGE_STYLE[key];
            return (
              <div
                key={key}
                className={`glass-card relative flex flex-col gap-3 p-5 text-center ${style.ring}`}
              >
                {style.badge && (
                  <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 rounded-full bg-gradient-to-br from-amber-300 to-amber-500 px-3 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-950 shadow shadow-amber-500/30">
                    {style.badge}
                  </span>
                )}
                <Sparkles className={`mx-auto h-5 w-5 ${style.icon}`} />
                <div>
                  <p className="text-base font-semibold text-slate-50">{pkg.name}</p>
                  <p className="mt-2 text-2xl font-bold tracking-tight text-slate-50">
                    {pkg.credits} {declineAnaliza(pkg.credits)}
                  </p>
                  <p className="mt-2 text-xl font-semibold text-slate-50">
                    {formatPrice(pkg.price_pln_grosz)}
                  </p>
                  {perUnit !== null && (
                    <p className="text-[11px] text-muted-foreground">
                      {formatPrice(perUnit)} / analiza
                    </p>
                  )}
                  <p className="mt-2 text-xs leading-snug text-slate-400 opacity-70">
                    {style.description}
                  </p>
                </div>
                <button
                  onClick={() => handleBuy(key)}
                  disabled={buyingPackage !== null}
                  className={`mt-auto inline-flex items-center justify-center gap-1.5 rounded-full px-5 py-2.5 text-sm font-medium transition disabled:opacity-60 ${style.button}`}
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

      {summary && summary.purchases.length > 0 && (
        <div className="glass-card flex flex-col gap-3 p-5">
          <div className="flex items-center gap-2">
            <Receipt className="h-4 w-4 text-emerald-400" />
            <p className="text-sm font-medium text-slate-200">Historia zakupów</p>
          </div>
          <div className="flex flex-col divide-y divide-border/40">
            {summary.purchases.map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                <div>
                  <p className="text-sm text-slate-200">
                    {packages?.[p.package as BillingPackageKey]?.label ?? p.package}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {p.completed_at ? new Date(p.completed_at).toLocaleDateString("pl-PL") : "—"} · +{p.credits} {declineAnaliza(p.credits)}
                  </p>
                </div>
                <p className="text-sm font-medium text-slate-300">{formatPrice(p.amount_pln_grosz)}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
