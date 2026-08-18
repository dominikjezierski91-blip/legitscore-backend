"use client";

import Link from "next/link";
import { XCircle } from "lucide-react";

export default function BillingCancelledPage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 py-16 text-center">
      <div className="glass-card flex max-w-sm flex-col items-center gap-4 p-8">
        <XCircle className="h-10 w-10 text-slate-500" />
        <div>
          <p className="text-lg font-semibold text-slate-50">Płatność anulowana</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Nic nie pobraliśmy z Twojej karty. Możesz spróbować ponownie w dowolnym momencie.
          </p>
        </div>
        <Link
          href="/billing"
          className="mt-1 inline-flex items-center justify-center gap-1.5 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 shadow-md shadow-emerald-500/30 transition hover:bg-emerald-400"
        >
          Wróć do cennika
        </Link>
      </div>
    </div>
  );
}
