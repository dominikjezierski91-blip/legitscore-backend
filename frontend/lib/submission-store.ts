export type PendingSubmission = {
  caseId: string;
  mode: "basic" | "expert";
  inputType: "photos" | "url";
  fileData?: Array<{ name: string; type: string; buffer: ArrayBuffer }>;
  auctionUrl?: string;
};

const SESSION_KEY = "ls_pending_submission";

let pending: PendingSubmission | null = null;

export function setPendingSubmission(submission: PendingSubmission) {
  pending = submission;
  if (typeof sessionStorage !== "undefined") {
    try {
      const { fileData: _, ...meta } = submission;
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(meta));
    } catch {}
  }
}

export function getPendingSubmission(): PendingSubmission | null {
  if (pending) return pending;
  if (typeof sessionStorage !== "undefined") {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (raw) return JSON.parse(raw) as PendingSubmission;
    } catch {}
  }
  return null;
}

export function clearPendingSubmission() {
  pending = null;
  if (typeof sessionStorage !== "undefined") {
    try { sessionStorage.removeItem(SESSION_KEY); } catch {}
  }
}
