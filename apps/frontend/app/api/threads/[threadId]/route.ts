import { NextResponse } from "next/server";
import { readAuth0SessionCookie } from "@/lib/server/auth0-session";
import { restoreAgentThread } from "@/lib/server/supervisor";

type RouteContext = {
  params: Promise<{ threadId: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const session = readAuth0SessionCookie(request.headers.get("cookie"));
  if (!session) {
    return NextResponse.json({ error: "Auth0 user login is required" }, { status: 401 });
  }

  const { threadId } = await context.params;
  const thread = await restoreAgentThread(threadId, session);

  return NextResponse.json(thread);
}
