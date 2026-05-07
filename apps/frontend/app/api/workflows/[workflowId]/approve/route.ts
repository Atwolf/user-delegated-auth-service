import { NextResponse } from "next/server";
import { getWorkflow, rememberWorkflow } from "@/lib/server/workflow-store";
import { approveWorkflow } from "@/lib/server/supervisor";
import { readAuth0SessionCookie } from "@/lib/server/auth0-session";

type Context = {
  params: Promise<{ workflowId: string }>;
};

export async function POST(req: Request, context: Context) {
  const { workflowId } = await context.params;
  const session = readAuth0SessionCookie(req.headers.get("cookie"));
  if (!session) {
    return NextResponse.json({ error: "Auth0 user login is required" }, { status: 401 });
  }

  const cached = getWorkflow(workflowId);
  if (!cached) {
    return NextResponse.json({ error: "workflow not found" }, { status: 404 });
  }

  const workflow = await approveWorkflow(workflowId, cached.plan_hash, session);
  rememberWorkflow(workflow);
  return NextResponse.json({ workflow });
}
