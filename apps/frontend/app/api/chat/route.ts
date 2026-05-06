import {
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage
} from "ai";
import { readAuth0SessionCookie } from "@/lib/server/auth0-session";
import { rememberWorkflow } from "@/lib/server/workflow-store";
import { planWorkflow } from "@/lib/server/supervisor";

export const maxDuration = 30;

export async function POST(req: Request) {
  const { messages }: { messages?: UIMessage[] } = await req.json();
  const session = readAuth0SessionCookie(req.headers.get("cookie"));
  const question = extractLastUserText(messages ?? []);

  return createUIMessageStreamResponse({
    stream: createUIMessageStream({
      async execute({ writer }) {
        const textId = "workflow-response";
        writer.write({ type: "text-start", id: textId });

        if (!session) {
          writer.write({
            type: "text-delta",
            id: textId,
            delta:
              "Auth0 user login is required before workflow planning. Log in with a user-scoped Auth0 account, then send the workflow request again."
          });
          writer.write({ type: "text-end", id: textId });
          return;
        }

        if (!question) {
          writer.write({
            type: "text-delta",
            id: textId,
            delta: "Send a workflow request after Auth0 user login succeeds."
          });
          writer.write({ type: "text-end", id: textId });
          return;
        }

        try {
          const workflow = await planWorkflow(question, session);
          rememberWorkflow(workflow);
          writer.write({
            type: "text-delta",
            id: textId,
            delta: [
              `User login active for ${session.userEmail ?? session.userId}.`,
              workflowStatusLine(workflow.workflow_id, workflow.status.status),
              workflow.status.status === "awaiting_approval"
                ? "Review the HITL manifest card before deterministic execution."
                : "Review the manifest card for the deterministic workflow plan.",
              `Telemetry: ${process.env.NEXT_PUBLIC_SIDECAR_URL ?? "http://localhost:4319/v1/telemetry"}`
            ].join("\n")
          });
        } catch (error) {
          const message = error instanceof Error ? error.message : "Workflow request failed";
          writer.write({
            type: "text-delta",
            id: textId,
            delta: `Workflow request failed: ${message}`
          });
        }

        writer.write({ type: "text-end", id: textId });
      }
    })
  });
}

function extractLastUserText(messages: UIMessage[]): string {
  const message = [...messages].reverse().find((item) => item.role === "user");
  if (!message) return "";

  const parts = Array.isArray(message.parts) ? message.parts : [];
  const text = parts
    .map((part) => {
      if (part.type === "text" && "text" in part && typeof part.text === "string") {
        return part.text;
      }
      return "";
    })
    .join(" ")
    .trim();

  return text;
}

function workflowStatusLine(workflowId: string, status: string): string {
  if (status === "ready") {
    return `Workflow ${workflowId} is ready; no HITL approval is required.`;
  }
  if (status === "awaiting_approval") {
    return `Workflow ${workflowId} is awaiting approval.`;
  }
  return `Workflow ${workflowId} is ${status.replace("_", " ")}.`;
}
