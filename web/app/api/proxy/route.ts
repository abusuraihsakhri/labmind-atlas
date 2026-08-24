import { NextRequest, NextResponse } from "next/server";

const AGENT_API = process.env.AGENT_API_URL || "http://localhost:8001";
const TIER2_TOKEN = process.env.TIER2_AUTH_SECRET || "";
const TIER3_TOKEN = process.env.TIER3_AUTH_SECRET || "";

const ALLOWED_GET_PATHS = new Set([
  "/specimens",
  "/actions",
  "/admin/stage",
  "/audit",
  "/health",
  "/metrics",
]);

const ALLOWED_POST_PATHS = new Set([
  "/admin/stage",
  "/supervisor/chat",
  "/admin/erasure/request",
]);

const ACTION_SUBPATH_REGEX = /^\/actions\/[a-zA-Z0-9_-]+\/(approve|dismiss)$/;
const ALERT_SUBPATH_REGEX = /^\/alerts\/[a-zA-Z0-9_-]+\/ack$/;

function validatePath(path: string, method: "GET" | "POST"): boolean {
  if (method === "GET") {
    return ALLOWED_GET_PATHS.has(path);
  }
  return (
    ALLOWED_POST_PATHS.has(path) ||
    ACTION_SUBPATH_REGEX.test(path) ||
    ALERT_SUBPATH_REGEX.test(path)
  );
}

function getAuthHeader(role: string): string {
  return role === "Administrator (Tier 3)" ? `Bearer ${TIER3_TOKEN}` : `Bearer ${TIER2_TOKEN}`;
}

async function proxyRequest(
  request: NextRequest,
  path: string,
  role: string,
  options: { method?: string; body?: unknown } = {}
) {
  const headers: Record<string, string> = {
    Authorization: getAuthHeader(role),
  };

  if (options.body) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${AGENT_API}${path}`, {
    method: options.method || request.method,
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });

  const data = await res.json().catch(() => null);
  return NextResponse.json(data, { status: res.status });
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const role = searchParams.get("role") || "Operator (Tier 2)";
  const path = searchParams.get("path") || "/specimens";

  if (!validatePath(path, "GET")) {
    return NextResponse.json({ error: "Access denied: Path not allowed." }, { status: 403 });
  }

  return proxyRequest(request, path, role);
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const role = (body as Record<string, string>)._role || "Operator (Tier 2)";
  const path = (body as Record<string, string>)._path || "";
  const { _role, _path, ...payload } = body as Record<string, unknown>;

  if (!validatePath(path, "POST")) {
    return NextResponse.json({ error: "Access denied: Path not allowed." }, { status: 403 });
  }

  return proxyRequest(request, path, role, { method: "POST", body: payload });
}
