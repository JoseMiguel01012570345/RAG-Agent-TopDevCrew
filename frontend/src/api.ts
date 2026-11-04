export type Community = {
  id: string;
  name: string;
  created_at: string;
};

export type DocumentRow = {
  id: string;
  community_id: string;
  filename: string;
  status: "pending" | "processing" | "ready" | "failed";
  error_code: string | null;
  error_message: string | null;
  page_count: number | null;
  created_at: string;
};

export type Citation = {
  document_id: string;
  document_name: string;
  page: number;
  fragment: string;
};

export type Answer = {
  answer: string;
  citations: Citation[];
  sufficient_evidence: boolean;
  degraded: boolean;
};

const USER_KEY = "faro.userId";

export function loadUserId(): string {
  return localStorage.getItem(USER_KEY) ?? "admin.demo";
}

export function saveUserId(userId: string): void {
  localStorage.setItem(USER_KEY, userId);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, userId: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-User-Id", userId);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText || "Error inesperado";
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // La respuesta no traía JSON.
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function listCommunities(userId: string): Promise<Community[]> {
  return request("/communities", userId);
}

export function createCommunity(userId: string, name: string): Promise<Community> {
  return request("/communities", userId, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function listDocuments(userId: string, communityId: string): Promise<DocumentRow[]> {
  return request(`/communities/${communityId}/documents`, userId);
}

export function deleteCommunity(userId: string, communityId: string): Promise<void> {
  return request(`/communities/${communityId}`, userId, { method: "DELETE" });
}

export function deleteDocument(
  userId: string,
  communityId: string,
  documentId: string,
): Promise<void> {
  return request(`/communities/${communityId}/documents/${documentId}`, userId, {
    method: "DELETE",
  });
}

export function uploadDocument(userId: string, communityId: string, file: File): Promise<DocumentRow> {
  const body = new FormData();
  body.append("file", file);
  return request(`/communities/${communityId}/documents`, userId, {
    method: "POST",
    body,
  });
}

export function askQuestion(userId: string, communityId: string, question: string): Promise<Answer> {
  return request(`/communities/${communityId}/questions`, userId, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}
