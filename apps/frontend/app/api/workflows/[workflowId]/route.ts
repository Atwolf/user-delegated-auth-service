import { NextResponse } from "next/server";
import { readAuth0SessionCookie } from "@/lib/server/auth0-session";
import { restoreAgentWorkflow } from "@/lib/server/supervisor";

type RouteContext = {
  params: Promise<{ workflowId: string }>;
};

export async function GET(request: Request, context: RouteContext) {
  const session = readAuth0SessionCookie(request.headers.get("cookie"));
  if (!session) {
    return NextResponse.json({ error: "Auth0 user login is required" }, { status: 401 });
  }

  const { workflowId } = await context.params;
  const workflow = await restoreAgentWorkflow(workflowId, session);

  return NextResponse.json(workflow);
}
