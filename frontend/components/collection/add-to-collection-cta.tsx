"use client";

import { useState, useEffect } from "react";
import { BookmarkPlus, BookmarkCheck } from "lucide-react";
import { getCollection } from "@/lib/api";
import { AddToCollectionModal } from "./add-to-collection-modal";

type Props = {
  caseId: string;
  mode?: string;
  reportData: any;
  autoOpen?: boolean;
};

export function AddToCollectionCta({ caseId, mode, reportData, autoOpen }: Props) {
  const [open, setOpen] = useState(autoOpen ?? false);
  const [alreadySaved, setAlreadySaved] = useState(false);

  useEffect(() => {
    getCollection()
      .then((items: any[]) => {
        if (items.some((i) => i.case_id === caseId)) {
          setAlreadySaved(true);
        }
      })
      .catch(() => {});
  }, [caseId]);

  if (alreadySaved) {
    return (
      <button
        disabled
        className="inline-flex w-full cursor-default items-center justify-center gap-2 rounded-full border border-slate-600/40 bg-slate-800/30 px-4 py-2.5 text-xs font-medium text-slate-500"
      >
        <BookmarkCheck className="h-3.5 w-3.5" />
        Dodane do kolekcji
      </button>
    );
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex w-full items-center justify-center gap-2 rounded-full border border-emerald-400/60 bg-emerald-500/10 px-4 py-2.5 text-xs font-medium text-emerald-200 transition hover:bg-emerald-500/20"
      >
        <BookmarkPlus className="h-3.5 w-3.5" />
        Dodaj do swojej kolekcji
      </button>

      {open && (
        <AddToCollectionModal
          caseId={caseId}
          mode={mode}
          reportData={reportData}
          onClose={() => setOpen(false)}
          onSaved={() => setAlreadySaved(true)}
        />
      )}
    </>
  );
}
