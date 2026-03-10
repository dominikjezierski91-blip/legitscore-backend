export type PendingSubmission = {
  caseId: string;
  mode: "basic" | "expert";
  files: File[];
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

