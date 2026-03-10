import { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

type ShellProps = {
  children: ReactNode;
  className?: string;
  subtitle?: string;
};

export function Shell({ children, className, subtitle }: ShellProps) {
  return (
    <div className="min-h-screen gradient-bg">
      <div className="mx-auto flex min-h-screen max-w-4xl flex-col px-4 py-6 md:px-6 lg:px-8">
        <header className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="rounded-full bg-slate-900/80 px-3 py-1 text-xs font-semibold tracking-wide text-slate-100 shadow-lg shadow-emerald-500/20">
              LegitScore
            </div>
            <Badge className="border-emerald-400/40 bg-emerald-500/10 text-emerald-300">
              BETA
            </Badge>
          </div>
          {subtitle ? (
            <span className="text-xs text-muted-foreground">{subtitle}</span>
          ) : null}
        </header>

        <main className={cn("flex flex-1 flex-col", className)}>{children}</main>

        <footer className="mt-10 border-t border-border/60 pt-4 text-center text-xs text-muted-foreground">
          <p>© 2026 LegitScore. Wszystkie prawa zastrzeżone.</p>
          <p className="mt-1">
            LegitScore dostarcza analizy ryzyka autentyczności koszulek
            piłkarskich. Raport nie stanowi certyfikatu ani gwarancji.
          </p>
        </footer>
      </div>
    </div>
  );
}

