"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Global error:", error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="max-w-md space-y-4 rounded-2xl border border-red-500/40 bg-slate-900 p-6 text-sm">
        <h2 className="font-semibold text-red-400">Błąd aplikacji</h2>
        <p className="font-mono text-xs text-slate-300 break-all">{error.message}</p>
        {error.digest && (
          <p className="text-[10px] text-slate-500">digest: {error.digest}</p>
        )}
        <button
          onClick={reset}
          className="rounded-full bg-emerald-500 px-4 py-2 text-xs font-medium text-slate-950"
        >
          Spróbuj ponownie
        </button>
      </div>
    </div>
  );
}
