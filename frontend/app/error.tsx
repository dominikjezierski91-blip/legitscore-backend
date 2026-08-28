"use client";

import { useEffect } from "react";

const CHUNK_ERROR_PATTERN = /Loading chunk .* failed|ChunkLoadError|failed to fetch dynamically imported module/i;
const RELOAD_GUARD_KEY = "ls_chunk_error_reload";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const isChunkError = CHUNK_ERROR_PATTERN.test(error.message);

  useEffect(() => {
    console.error("Global error:", error);

    // Stary chunk JS (np. z HTML zbuforowanego sprzed nowego deployu) już nie istnieje
    // na serwerze — samo `reset()` tylko ponownie renderuje drzewo React, nie pobiera
    // nowego HTML/mapowania chunków, więc błąd wraca w kółko. Trzeba pełnego przeładowania.
    if (isChunkError && !sessionStorage.getItem(RELOAD_GUARD_KEY)) {
      sessionStorage.setItem(RELOAD_GUARD_KEY, "1");
      window.location.reload();
    }
  }, [error, isChunkError]);

  if (isChunkError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
        <div className="max-w-md space-y-4 rounded-2xl border border-emerald-500/40 bg-slate-900 p-6 text-sm">
          <h2 className="font-semibold text-emerald-400">Dostępna nowa wersja aplikacji</h2>
          <p className="text-xs text-slate-300">Odświeżamy stronę, żeby wczytać aktualną wersję...</p>
          <button
            onClick={() => window.location.reload()}
            className="rounded-full bg-emerald-500 px-4 py-2 text-xs font-medium text-slate-950"
          >
            Odśwież teraz
          </button>
        </div>
      </div>
    );
  }

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
