import { getToken } from "@/lib/auth";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

if (!API_BASE_URL) {
  // eslint-disable-next-line no-console
  console.warn(
    "NEXT_PUBLIC_API_BASE_URL is not set. API calls from LegitScore frontend will fail until it is configured."
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error("Brak konfiguracji backendu (NEXT_PUBLIC_API_BASE_URL).");
  }

  const url = `${API_BASE_URL.replace(/\/$/, "")}${path}`;
  const token = getToken();
  const res = await fetch(url, {
    ...init,
    headers: {
      ...(init && init.headers),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  if (!res.ok) {
    let detail: string | undefined;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") {
        detail = data.detail;
      } else if (data?.detail && typeof data.detail === "object") {
        // Obsługa błędów precheck z message
        detail = data.detail.message || JSON.stringify(data.detail);
      } else {
        detail = JSON.stringify(data?.detail ?? data);
      }
    } catch {
      detail = res.statusText;
    }
    throw new Error(detail || `Request failed with status ${res.status}`);
  }

  // run-decision may return JSON object; some endpoints return simple objects
  const text = await res.text();
  if (!text) {
    return {} as T;
  }
  return JSON.parse(text) as T;
}

export async function createCase(
  email?: string,
  offerLink?: string,
  context?: string
): Promise<{ case_id: string }> {
  return request<{ case_id: string }>("/api/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: email || null,
      offer_link: offerLink || null,
      context: context || null,
    }),
  });
}

export async function uploadAssets(
  caseId: string,
  files: File[]
): Promise<{ assets: unknown[] }> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }

  return request<{ assets: unknown[] }>(`/api/cases/${caseId}/assets`, {
    method: "POST",
    body: form,
  });
}

export async function runDecision(
  caseId: string,
  mode: "basic" | "expert"
): Promise<unknown> {
  const q = mode === "expert" ? "expert" : "basic";
  return request(`/api/cases/${caseId}/run-decision?mode=${q}`, {
    method: "POST",
  });
}

export async function getCase(caseId: string): Promise<unknown> {
  return request(`/api/cases/${caseId}`);
}

export async function submitFeedback(
  caseId: string,
  feedback: "correct" | "incorrect" | "unsure",
  comment?: string
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/cases/${caseId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feedback, comment }),
  });
}

export async function getFeedback(
  caseId: string
): Promise<{ feedback: string | null; feedback_at: string | null; comment: string | null }> {
  return request(`/api/cases/${caseId}/feedback`);
}

export async function submitRating(
  caseId: string,
  rating: number,
  comment?: string
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/cases/${caseId}/rating`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating, comment: comment || null }),
  });
}

export async function getRating(
  caseId: string
): Promise<{ rating: number | null; rating_at: string | null }> {
  return request(`/api/cases/${caseId}/rating`);
}

export async function importFromUrl(
  caseId: string,
  url: string
): Promise<{ ok: boolean; assets: unknown[]; count: number }> {
  return request<{ ok: boolean; assets: unknown[]; count: number }>(
    `/api/cases/${caseId}/import-from-url`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }
  );
}

// ── Auth ─────────────────────────────────────────────────────

export async function authRegister(
  email: string,
  password: string,
  passwordConfirm: string
): Promise<{ token: string; user: { id: string; email: string; is_admin: boolean } }> {
  return request("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, password_confirm: passwordConfirm }),
  });
}

export async function authLogin(
  email: string,
  password: string
): Promise<{ token: string; user: { id: string; email: string; is_admin: boolean } }> {
  return request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export type AuthMeResponse = {
  id: string;
  email: string;
  is_admin: boolean;
  user_type: string | null;
  collection_size_range: string | null;
  profile_survey_completed_at: string | null;
  profile_survey_skipped_at: string | null;
};

export async function authMe(): Promise<AuthMeResponse> {
  return request("/api/auth/me");
}

export async function submitProfileSurvey(
  userType: string,
  collectionSizeRange: string,
): Promise<void> {
  await request("/api/auth/profile-survey", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_type: userType, collection_size_range: collectionSizeRange }),
  });
}

export async function skipProfileSurvey(): Promise<void> {
  await request("/api/auth/profile-survey/skip", { method: "POST" });
}

export async function updateUserProfile(
  userType: string | null,
  collectionSizeRange: string | null,
): Promise<void> {
  await request("/api/auth/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_type: userType, collection_size_range: collectionSizeRange }),
  });
}

// ── Collection ───────────────────────────────────────────────

export type CollectionItemPayload = {
  case_id: string;
  report_mode?: string;
  club?: string;
  season?: string;
  model_type?: string;
  brand?: string;
  player_name?: string;
  player_number?: string;
  verdict_category?: string;
  confidence_percent?: number;
  confidence_level?: string;
  sku?: string;
  report_id?: string;
  analysis_date?: string;
  purchase_price?: string;
  purchase_currency?: string;
  purchase_date?: string;
  purchase_source?: string;
  notes?: string;
};

export async function addToCollection(data: CollectionItemPayload): Promise<unknown> {
  return request("/api/collection", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function getCollection(): Promise<CollectionItemPayload[]> {
  return request("/api/collection");
}

export async function deleteFromCollection(itemId: string): Promise<{ ok: boolean }> {
  return request(`/api/collection/${itemId}`, { method: "DELETE" });
}

export async function refreshMarketValue(itemId: string): Promise<any> {
  return request(`/api/collection/${itemId}/market-value`, { method: "POST" });
}

export async function updateCollectionItem(
  itemId: string,
  data: Partial<{
    club: string; season: string; model_type: string; brand: string;
    player_name: string; player_number: string; verdict_category: string;
    purchase_price: string; purchase_currency: string;
    purchase_date: string; purchase_source: string; notes: string;
  }>
): Promise<any> {
  return request(`/api/collection/${itemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function uploadCollectionPhoto(itemId: string, file: File): Promise<{ ok: boolean }> {
  const form = new FormData();
  form.append("file", file);
  return request(`/api/collection/${itemId}/photo`, { method: "POST", body: form });
}

export function getCollectionThumbnailUrl(itemId: string): string {
  const base = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");
  return `${base}/api/collection/${itemId}/thumbnail`;
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return request("/api/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export async function deleteAccount(): Promise<void> {
  return request("/api/auth/delete-account", { method: "DELETE" });
}

export async function exportUserData(): Promise<any> {
  return request("/api/auth/export-data", { method: "GET" });
}

export interface SupportPayload {
  type: string;
  message: string;
  email: string;
  wants_reply?: boolean;
  user_id?: string;
  auth_state?: string;
  source_page?: string;
  current_url?: string;
  app_section?: string;
  report_id?: string;
  analysis_id?: string;
  shirt_id?: string;
  collection_item_id?: string;
}

export async function submitSupport(data: SupportPayload): Promise<{ ok: boolean; id: string }> {
  return request("/api/support", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}
