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
  const res = await fetch(url, {
    ...init,
    headers: {
      ...(init && init.headers),
    },
  });

  if (!res.ok) {
    let detail: string | undefined;
    try {
      const data = await res.json();
      detail =
        typeof data?.detail === "string"
          ? data.detail
          : JSON.stringify(data?.detail ?? data);
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

export async function createCase(): Promise<{ case_id: string }> {
  return request<{ case_id: string }>("/api/cases", {
    method: "POST",
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

