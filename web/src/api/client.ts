import type { EdgeRequest, EdgeResponse, ExplainRequest, ExplainResponse, ExploreResponse, GraphResponse, Profile, ProfileDetail, SelectionRequest } from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(`API error ${status}: ${detail}`);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return (await response.json()) as T;
}

function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export const api = {
  graph(actions: string[] = [], signal?: AbortSignal): Promise<GraphResponse> {
    const query = new URLSearchParams(actions.map((action) => ["action", action]));
    const suffix = actions.length > 0 ? `?${query}` : "";
    return request<GraphResponse>(`/api/graph${suffix}`, { signal });
  },

  profiles(signal?: AbortSignal): Promise<Profile[]> {
    return request<Profile[]>("/api/profiles", { signal });
  },

  profile(id: string, signal?: AbortSignal): Promise<ProfileDetail> {
    return request<ProfileDetail>(`/api/profiles/${encodeURIComponent(id)}`, { signal });
  },

  explore(selection: SelectionRequest, signal?: AbortSignal): Promise<ExploreResponse> {
    return postJson<ExploreResponse>("/api/explore", selection, signal);
  },

  explain(request: ExplainRequest, signal?: AbortSignal): Promise<ExplainResponse> {
    return postJson<ExplainResponse>("/api/explain", request, signal);
  },

  explainEdge(request: EdgeRequest, signal?: AbortSignal): Promise<EdgeResponse> {
    return postJson<EdgeResponse>("/api/explain-edge", request, signal);
  },
};
