// Thin fetch wrappers around the FastAPI backend. Server-authoritative: the
// client sends state/actions and renders what comes back — it computes no
// combat math itself.

import type {
  JudgeRequest,
  JudgeResponse,
  NewMatchResponse,
  ResolveRequest,
  ResolveResult,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export function newMatch(p1_name: string, p2_name: string): Promise<NewMatchResponse> {
  return post<NewMatchResponse>("/api/new_match", { p1_name, p2_name });
}

export function judge(req: JudgeRequest): Promise<JudgeResponse> {
  return post<JudgeResponse>("/api/judge", req);
}

export function resolve(req: ResolveRequest): Promise<ResolveResult> {
  return post<ResolveResult>("/api/resolve", req);
}
