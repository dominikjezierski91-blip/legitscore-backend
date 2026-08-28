import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Poprawna polska odmiana rzeczownika "analiza" (analiza/analizy/analiz),
 * z regułą 11-14 -> zawsze dopełniacz (np. "12 analiz", nie "12 analizy"). */
export function declineAnaliza(n: number): string {
  if (n === 1) return "analiza";
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return "analizy";
  return "analiz";
}

