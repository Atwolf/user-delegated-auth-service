import { NextResponse } from "next/server";
import { getWorkflow, rememberWorkflow } from "@/lib/server/workflow-store";
import { approveWorkflow } from "@/lib/server/supervisor";

type Context = {
  params: Promise<{ workflowId: string }>;
};

export async function POST(req: Request, context: Context) {
  const { workflowId } = await context.params;
  const body = (await req.json().catch(() => ({}))) as { tokenRef?: string | null };
  const cached = getWorkflow(workflowId);
  if (!cached) {
    return NextResponse.json({ error: "workflow not found" }, { status: 404 });
  }

  const workflow = await approveWorkflow(workflowId, cached.plan_hash, body.tokenRef ?? null);
  rememberWorkflow(workflow);
  return NextResponse.json({ workflow });
}
