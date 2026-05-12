import { NextResponse } from "next/server";
import { readAuth0SessionCookie } from "@/lib/server/auth0-session";
import { createAgentThread } from "@/lib/server/supervisor";

export async function POST(req: Request) {
  const session = readAuth0SessionCookie(req.headers.get("cookie"));
  if (!session) {
    return NextResponse.json({ error: "Auth0 user login is required" }, { status: 401 });
  }

  const payload = await req.json().catch(() => ({}));
  const title =
    payload && typeof payload === "object" && "title" in payload && typeof payload.title === "string"
      ? payload.title
      : null;
  const thread = await createAgentThread(session, { title });

  return NextResponse.json(thread);
}
