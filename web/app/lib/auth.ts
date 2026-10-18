import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export type DashboardRole = "Operator (Tier 2)" | "Administrator (Tier 3)";
const COOKIE_NAME = "labmind_session";
const SESSION_SECONDS = 60 * 60;

export { COOKIE_NAME };

function sessionSecret(): string | null {
  const secret = process.env.DASHBOARD_SESSION_SECRET;
  return secret && secret.length >= 32 ? secret : null;
}
function passwordMatches(provided: string, configured: string | undefined): boolean {
  if (!configured || configured.length < 16 || typeof provided !== "string") return false;
  const first = createHash("sha256").update(provided).digest();
  const second = createHash("sha256").update(configured).digest();
  return timingSafeEqual(first, second);
}
export function authenticateDashboard(role: unknown, password: unknown): DashboardRole | null {
  if (!sessionSecret() || typeof password !== "string" || password.length > 1024) return null;
  if (role === "Administrator (Tier 3)" &&
      passwordMatches(password, process.env.DASHBOARD_TIER3_PASSWORD)) return role;
  if (role === "Operator (Tier 2)" &&
      passwordMatches(password, process.env.DASHBOARD_TIER2_PASSWORD)) return role;
  return null;
}
export function createSession(role: DashboardRole): string {
  const secret = sessionSecret();
  if (!secret) throw new Error("Dashboard authentication not configured");
  const payload = Buffer.from(JSON.stringify({
    role, exp: Math.floor(Date.now() / 1000) + SESSION_SECONDS,
    nonce: randomBytes(12).toString("hex")
  })).toString("base64url");
  const signature = createHmac("sha256", secret).update(payload).digest("base64url");
  return payload + "." + signature;
}
export function verifySession(cookie: string | undefined): DashboardRole | null {
  const secret = sessionSecret();
  if (!secret || !cookie || cookie.length > 4096) return null;
  const parts = cookie.split(".");
  if (parts.length !== 2) return null;
  const expected = createHmac("sha256", secret).update(parts[0]).digest();
  let supplied: Buffer;
  try { supplied = Buffer.from(parts[1], "base64url"); } catch { return null; }
  if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) return null;
  try {
    const value: unknown = JSON.parse(Buffer.from(parts[0], "base64url").toString("utf8"));
    if (!value || typeof value !== "object") return null;
    const { role, exp } = value as { role?: unknown; exp?: unknown };
    if (role !== "Operator (Tier 2)" && role !== "Administrator (Tier 3)") return null;
    if (typeof exp !== "number" || !Number.isSafeInteger(exp) ||
        exp <= Date.now() / 1000 || exp > Date.now() / 1000 + SESSION_SECONDS + 60) return null;
    return role;
  } catch { return null; }
}
export function authConfigured(): boolean {
  return Boolean(sessionSecret() &&
    process.env.DASHBOARD_TIER2_PASSWORD && process.env.DASHBOARD_TIER2_PASSWORD.length >= 16 &&
    process.env.DASHBOARD_TIER3_PASSWORD && process.env.DASHBOARD_TIER3_PASSWORD.length >= 16);
}
export const SESSION_MAX_AGE = SESSION_SECONDS;
