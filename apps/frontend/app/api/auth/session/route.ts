import { NextResponse } from "next/server";
import { readAuth0SessionCookie } from "@/lib/server/auth0-session";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const session = readAuth0SessionCookie(req.headers.get("cookie"));
  if (!session) return NextResponse.json({ session: null });
  const safeSession = { ...session };
  delete safeSession.authContextRef;
  return NextResponse.json({ session: safeSession });
}
