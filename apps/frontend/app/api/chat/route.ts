import {
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage
} from "ai";
import { decodeAuth0ConfigHeader, validateAuth0Config } from "@/lib/auth0-config";
import { rememberWorkflow } from "@/lib/server/workflow-store";
import { exchangeClientCredentials, planWorkflow } from "@/lib/server/supervisor";

export const maxDuration = 30;

export async function POST(req: Request) {
  const { messages }: { messages?: UIMessage[] } = await req.json();
  const config = decodeAuth0ConfigHeader(req.headers.get("x-auth0-config"));
  const question = extractLastUserText(messages ?? []);

  return createUIMessageStreamResponse({
    stream: createUIMessageStream({
      async execute({ writer }) {
        const textId = "workflow-response";
        writer.write({ type: "text-start", id: textId });

        if (!config || !validateAuth0Config(config).valid) {
          writer.write({
            type: "text-delta",
            id: textId,
            delta:
              "Auth0 Client Credentials config is missing or incomplete. Fill the configuration panel, keep the client secret in memory, then send the workflow request again."
          });
          writer.write({ type: "text-end", id: textId });
          return;
        }

        if (!question) {
          writer.write({
            type: "text-delta",
            id: textId,
            delta: "Send a workflow request after the Auth0 Client Credentials config is valid."
          });
          writer.write({ type: "text-end", id: textId });
          return;
        }

        try {
          const token = await exchangeClientCredentials(config);
          const workflow = await planWorkflow(question, token.token_ref, token.scope);
          rememberWorkflow(workflow);
          writer.write({
            type: "text-delta",
            id: textId,
            delta: [
              `Token exchange succeeded for ${config.domain}.`,
              `Workflow ${workflow.workflow_id} is awaiting approval.`,
              `Review the manifest card before deterministic execution.`,
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
