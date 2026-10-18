import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME, verifySession } from "./app/lib/auth";

export function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (path === "/login" || path.startsWith("/api/") ||
      path.startsWith("/_next/") || path === "/favicon.ico") {
    return NextResponse.next();
  }
  if (!verifySession(request.cookies.get(COOKIE_NAME)?.value)) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}
export const config = { matcher: ["/", "/audit", "/login"] };
