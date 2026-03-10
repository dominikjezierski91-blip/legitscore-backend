"use client";

import { useCallback, useRef, useState } from "react";
import { ImageIcon, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";

export type MultiImageUploaderProps = {
  files: File[];
  onChange: (files: File[]) => void;
  minCount?: number;
};

export function MultiImageUploader({
  files,
  onChange,
  minCount = 7,
}: MultiImageUploaderProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const maxCount = 12;

  const handleFiles = useCallback(
    (list: FileList | null) => {
      if (!list) return;
      const incoming = Array.from(list);
      const availableSlots = maxCount - files.length;

      if (availableSlots <= 0) {
        setWarning("Maksymalna liczba zdjęć to 12.");
        return;
      }

      const toAdd = incoming.slice(0, availableSlots);
      if (incoming.length > availableSlots) {
        setWarning("Maksymalna liczba zdjęć to 12.");
      } else {
        setWarning(null);
      }

      const next = [...files, ...toAdd];
      onChange(next);
    },
    [files, onChange]
  );

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    handleFiles(e.dataTransfer.files);
  };

  const onRemove = (index: number) => {
    const next = files.filter((_, i) => i !== index);
    onChange(next);
  };

  const hasEnough = files.length >= minCount;
  const progress = Math.min(1, files.length / minCount);
  const remaining = Math.max(0, minCount - files.length);

  return (
    <section className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
        }}
        onDrop={onDrop}
        className={cn(
          "flex min-h-[140px] flex-col items-center justify-center rounded-2xl border border-dashed border-border/80 bg-slate-950/40 px-4 text-xs text-muted-foreground transition-colors",
          "hover:border-emerald-400/70 hover:bg-slate-900/60"
        )}
        onClick={() => inputRef.current?.click()}
      >
        <ImageIcon className="mb-2 h-6 w-6 text-emerald-300" />
        <div className="mb-1 text-[11px] font-medium text-slate-100">
          Przeciągnij zdjęcia lub kliknij, aby wybrać
        </div>
        <div className="text-[11px]">
          JPG, PNG • maks. {maxCount} zdjęć
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      <div className="space-y-1 text-[11px] text-muted-foreground">
        <div className="flex items-center justify-between">
          <span>
            {files.length} z {minCount} wymaganych zdjęć
          </span>
          <span
            className={cn(
              "font-semibold",
              hasEnough ? "text-emerald-300" : "text-amber-300"
            )}
          >
            {hasEnough
              ? "Minimalny wymóg spełniony"
              : `Brakuje jeszcze ${remaining}`}
          </span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800/80">
          <div
            className={cn(
              "h-1.5 rounded-full transition-all",
              hasEnough ? "bg-emerald-400" : "bg-amber-300"
            )}
            style={{ width: `${progress * 100}%` }}
          />
        </div>
      </div>

      {warning && (
        <div className="text-[11px] text-amber-300">{warning}</div>
      )}

      {files.length > 0 && (
        <div className="grid grid-cols-3 gap-2 md:grid-cols-4">
          {files.map((file, idx) => {
            const url = URL.createObjectURL(file);
            return (
              <div
                key={idx}
                className="group relative overflow-hidden rounded-xl border border-border/70 bg-slate-950/60"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={url}
                  alt={file.name}
                  className="h-24 w-full object-cover"
                />
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemove(idx);
                  }}
                  className="absolute right-1.5 top-1.5 inline-flex h-6 w-6 items-center justify-center rounded-full bg-slate-900/90 text-[10px] text-slate-200 opacity-0 shadow-md transition group-hover:opacity-100"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

