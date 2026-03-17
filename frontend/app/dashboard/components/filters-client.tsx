"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useCallback } from "react";

const VERDICT_OPTIONS = [
  { value: "", label: "Wszystkie werdykty" },
  { value: "meczowa", label: "Meczowa" },
  { value: "oryginalna_sklepowa", label: "Oryginalna" },
  { value: "oficjalna_replika", label: "Replika" },
  { value: "podrobka", label: "Podróbka" },
  { value: "edycja_limitowana", label: "Limitowana" },
  { value: "treningowa_custom", label: "Treningowa" },
];

const AUTH_OPTIONS = [
  { value: "", label: "Wszyscy" },
  { value: "logged_in", label: "Zalogowani" },
  { value: "guest", label: "Goście" },
];

export function DashboardFilters() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const update = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params.toString());
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
      router.push(`${pathname}?${next.toString()}`);
    },
    [router, pathname, params],
  );

  const sel =
    "rounded-lg border border-slate-600/60 bg-slate-800/60 px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-emerald-500/40";

  return (
    <div className="flex flex-wrap items-center gap-3">
      <input
        type="date"
        defaultValue={params.get("date_from") ?? ""}
        onChange={(e) => update("date_from", e.target.value)}
        className={sel}
        title="Od daty"
      />
      <span className="text-xs text-slate-600">—</span>
      <input
        type="date"
        defaultValue={params.get("date_to") ?? ""}
        onChange={(e) => update("date_to", e.target.value)}
        className={sel}
        title="Do daty"
      />
      <select
        defaultValue={params.get("auth_state") ?? ""}
        onChange={(e) => update("auth_state", e.target.value)}
        className={sel}
      >
        {AUTH_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <select
        defaultValue={params.get("verdict") ?? ""}
        onChange={(e) => update("verdict", e.target.value)}
        className={sel}
      >
        {VERDICT_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
