import { NextResponse } from "next/server";
import { getLatestWorkflow } from "@/lib/server/workflow-store";

export async function GET() {
  return NextResponse.json({ workflow: getLatestWorkflow() });
}
