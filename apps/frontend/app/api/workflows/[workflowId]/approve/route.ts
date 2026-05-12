import { NextResponse } from "next/server";
import { readAuth0SessionCookie } from "@/lib/server/auth0-session";
import { approveAgentWorkflow } from "@/lib/server/supervisor";

type RouteContext = {
  params: Promise<{ workflowId: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const session = readAuth0SessionCookie(request.headers.get("cookie"));
  if (!session) {
    return NextResponse.json({ error: "Auth0 user login is required" }, { status: 401 });
  }

  const payload = await request.json().catch(() => ({}));
  if (!isRecord(payload)) {
    return NextResponse.json({ error: "Approval payload must be an object" }, { status: 400 });
  }

  const approved = payload.approved;
  const planHash = payload.plan_hash ?? payload.planHash;
  if (typeof approved !== "boolean") {
    return NextResponse.json({ error: "approved must be a boolean" }, { status: 400 });
  }
  if (typeof planHash !== "string" || planHash.length === 0) {
    return NextResponse.json({ error: "plan_hash is required" }, { status: 400 });
  }

  const { workflowId } = await context.params;
  const approval = await approveAgentWorkflow(workflowId, session, {
    approved,
    planHash
  });

  return NextResponse.json(approval);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
