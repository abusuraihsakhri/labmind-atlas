import { NextRequest, NextResponse } from "next/server";
import { authenticateDashboard, authConfigured, COOKIE_NAME, createSession, SESSION_MAX_AGE, verifySession } from "../../lib/auth";

function sameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true; // SameSite=Strict cookie; non-browser clients may omit Origin.
  try { return new URL(origin).host === request.nextUrl.host; } catch { return false; }
}
export async function GET(request: NextRequest) {
  const role = verifySession(request.cookies.get(COOKIE_NAME)?.value);
  return NextResponse.json(role ? { role } : { error: "Authentication required" },
    { status: role ? 200 : 401, headers: { "Cache-Control": "no-store" } });
}
export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({error:"Origin not allowed"}, {status:403});
  if (!authConfigured()) return NextResponse.json({error:"Dashboard authentication is not configured on this server"}, {status:503});
  const data: unknown = await request.json().catch(() => null);
  if (!data || typeof data !== "object") return NextResponse.json({error:"Invalid credentials"}, {status:401});
  const {role, password} = data as {role?:unknown;password?:unknown};
  const authenticated = authenticateDashboard(role, password);
  if (!authenticated) return NextResponse.json({error:"Invalid credentials"}, {status:401});
  const response = NextResponse.json({role:authenticated}, {headers:{"Cache-Control":"no-store"}});
  response.cookies.set(COOKIE_NAME, createSession(authenticated), {
    path:"/", httpOnly:true, secure:process.env.NODE_ENV === "production", sameSite:"strict", maxAge:SESSION_MAX_AGE
  });
  return response;
}
export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({error:"Origin not allowed"}, {status:403});
  const response = NextResponse.json({status:"signed_out"}, {headers:{"Cache-Control":"no-store"}});
  response.cookies.set(COOKIE_NAME, "", {path:"/",httpOnly:true,sameSite:"strict",maxAge:0});
  return response;
}
