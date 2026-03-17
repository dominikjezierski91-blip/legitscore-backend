"use client";

import { useRouter } from "next/navigation";
import { ChevronLeft } from "lucide-react";

interface Props {
  fallback?: string;
  label?: string;
}

export function BackButton({ fallback = "/", label = "Wstecz" }: Props) {
  const router = useRouter();
  return (
    <button
      onClick={() => router.back()}
      className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition"
    >
      <ChevronLeft className="h-3.5 w-3.5" />
      {label}
    </button>
  );
}
