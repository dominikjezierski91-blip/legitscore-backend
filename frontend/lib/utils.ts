import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Poprawna polska odmiana rzeczownika "Legit" (wewnętrzna waluta = 1 analiza).
 * Pisane z dużej litery konsekwentnie w całej apce, jak nazwa własna (V-Bucks,
 * Robux), a nie zwykły rzeczownik pospolity. */
export function declineLegit(n: number): string {
  if (n === 1) return "Legit";
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return "Legity";
  return "Legitów";
}

