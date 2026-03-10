import "./globals.css";
import type { Metadata } from "next";
import { ReactNode } from "react";
import { Shell } from "@/components/layout/shell";

export const metadata: Metadata = {
  title: "LegitScore · Analiza ryzyka autentyczności koszulek",
  description:
    "LegitScore analizuje koszulki piłkarskie i generuje uporządkowany raport ryzyka autentyczności. Raport nie stanowi certyfikatu ani gwarancji.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pl" suppressHydrationWarning className="h-full">
      <body className="min-h-screen bg-background text-foreground antialiased">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}

