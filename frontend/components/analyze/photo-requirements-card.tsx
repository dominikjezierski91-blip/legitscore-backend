"use client";

export function PhotoRequirementsCard() {
  const required = [
    "przód koszulki",
    "tył koszulki",
    "metka wewnętrzna",
    "herb / emblemat",
    "logo producenta",
    "numer lub nazwisko",
    "szew / kołnierz",
  ];

  const optional = [
    "metka papierowa",
    "struktura materiału",
    "patch meczowy / detal",
  ];

  return (
    <section className="mt-3 rounded-2xl border border-emerald-500/20 bg-slate-900/60 p-4 text-xs text-muted-foreground">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-emerald-200">
        Jakie zdjęcia przygotować?
      </h3>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <div className="mb-2 text-[11px] font-semibold text-slate-100">
            Wymagane
          </div>
          <ul className="space-y-1">
            {required.map((item) => (
              <li key={item} className="flex items-center gap-2">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500/15 text-[10px] text-emerald-300">
                  ✓
                </span>
                <span className="text-[11px] text-slate-100">{item}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="mb-2 text-[11px] font-semibold text-slate-100">
            Opcjonalne
          </div>
          <ul className="space-y-1">
            {optional.map((item) => (
              <li key={item} className="flex items-center gap-2">
                <span className="flex h-3 w-3 items-center justify-center rounded-full border border-slate-500/70" />
                <span className="text-[11px] text-slate-200">{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

