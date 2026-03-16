export type PendingSubmission = {
  caseId: string;
  mode: "basic" | "expert";
  inputType: "photos" | "url";
  fileData?: Array<{ name: string; type: string; buffer: ArrayBuffer }>;
  auctionUrl?: string;
};

let pending: PendingSubmission | null = null;

export function setPendingSubmission(submission: PendingSubmission) {
  pending = submission;
}

export function getPendingSubmission(): PendingSubmission | null {
  return pending;
}

export function clearPendingSubmission() {
  pending = null;
}

