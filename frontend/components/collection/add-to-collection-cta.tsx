"use client";

import { useState } from "react";
import { BookmarkPlus } from "lucide-react";
import { AddToCollectionModal } from "./add-to-collection-modal";

type Props = {
  caseId: string;
  mode?: string;
  reportData: any;
  autoOpen?: boolean;
};

export function AddToCollectionCta({ caseId, mode, reportData, autoOpen }: Props) {
  const [open, setOpen] = useState(autoOpen ?? false);

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
        />
      )}
    </>
  );
}
