import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME, verifySession } from "../../lib/auth";

const AGENT_API = process.env.AGENT_API_URL || "http://localhost:8001";
const TIER2_TOKEN = process.env.TIER2_AUTH_SECRET || "";
const TIER3_TOKEN = process.env.TIER3_AUTH_SECRET || "";

const ALLOWED_GET_PATHS = new Set([
  "/specimens", "/actions", "/admin/stage", "/audit", "/health", "/metrics",
]);
const ALLOWED_POST_PATHS = new Set([
  "/admin/stage", "/supervisor/chat", "/admin/erasure/request",
]);
const ACTION_SUBPATH_REGEX = /^\/actions\/[a-zA-Z0-9_-]+\/(approve|dismiss)$/;
const ALERT_SUBPATH_REGEX = /^\/alerts\/[a-zA-Z0-9_-]+\/ack$/;

function validatePath(path: string, method: "GET" | "POST"): boolean {
  if (method === "GET") return ALLOWED_GET_PATHS.has(path);
  return ALLOWED_POST_PATHS.has(path) ||
    ACTION_SUBPATH_REGEX.test(path) || ALERT_SUBPATH_REGEX.test(path);
}
function checkOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try { return new URL(origin).host === request.nextUrl.host; } catch { return false; }
}
async function proxyRequest(request: NextRequest, path: string, method: "GET" | "POST", body?: unknown) {
  // Backend credentials are derived exclusively from the signed HTTP-only session.
  const role = verifySession(request.cookies.get(COOKIE_NAME)?.value);
  if (!role) return NextResponse.json({error:"Authentication required"}, {status:401});
  if (!validatePath(path, method)) return NextResponse.json({error:"Path not allowed"}, {status:403});
  if (method === "POST" && !checkOrigin(request)) return NextResponse.json({error:"Origin not allowed"}, {status:403});
  const token = role === "Administrator (Tier 3)" ? TIER3_TOKEN : TIER2_TOKEN;
  if (!token) return NextResponse.json({error:"Backend credentials not configured"}, {status:503});
  try {
    const response = await fetch(new URL(path, AGENT_API), {
      method,
      headers: {
        Authorization: "Bearer " + token,
        ...(method === "POST" ? {"Content-Type":"application/json"} : {})
      },
      ...(method === "POST" ? {body:JSON.stringify(body ?? {})} : {}),
      cache:"no-store",
      signal:AbortSignal.timeout(10000)
    });
    const data: unknown = await response.json().catch(() => ({error:"Unexpected upstream response"}));
    return NextResponse.json(data, {status:response.status, headers:{"Cache-Control":"no-store"}});
  } catch {
    return NextResponse.json({error:"Agent service unavailable"}, {status:502, headers:{"Cache-Control":"no-store"}});
  }
}
export async function GET(request: NextRequest) {
  const path = request.nextUrl.searchParams.get("path") || "/specimens";
  return proxyRequest(request, path, "GET");
}
export async function POST(request: NextRequest) {
  const input: unknown = await request.json().catch(() => null);
  if (!input || typeof input !== "object" || Array.isArray(input))
    return NextResponse.json({error:"Invalid JSON request"}, {status:400});
  const {_path, _role: _discardRole, ...payload} = input as Record<string, unknown>;
  void _discardRole;
  if (typeof _path !== "string") return NextResponse.json({error:"Invalid path"}, {status:400});
  return proxyRequest(request, _path, "POST", payload);
}
