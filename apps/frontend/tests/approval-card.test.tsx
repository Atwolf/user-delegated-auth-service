import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApprovalCard } from "@/components/approval-card";
import type { WorkflowRecord } from "@/lib/workflow-types";

const workflow: WorkflowRecord = {
  workflow_id: "wf-123",
  status: { status: "awaiting_approval" },
  plan_hash: "sha256:abc",
  authorization: {
    workflow_id: "wf-123",
    scopes: ["DOE.Identity.sample-user"],
    proposals: [
      {
        agent_name: "identity",
        tool_name: "get_identity_profile",
        arguments: { subject_user_id: "sample-user" },
        reason: "identity"
      }
    ]
  },
  plan: {
    workflow_id: "wf-123",
    user_id: "sample-user",
    session_id: "sample-session",
    created_at: new Date().toISOString(),
    steps: [
      {
        step_id: "step-001",
        target_agent: "identity",
        action: "get_identity_profile",
        input_model_type: "get_identity_profile.arguments",
        input_payload_json: JSON.stringify({ subject_user_id: "sample-user" }),
        required_scopes: ["DOE.Identity.sample-user"],
        mutates_external_state: false
      }
    ]
  },
  events: [],
  step_results: []
};

describe("ApprovalCard", () => {
  it("renders manifest steps, arguments, scopes, and approval action", () => {
    const onApprove = vi.fn();
    render(<ApprovalCard workflow={workflow} onApprove={onApprove} />);

    expect(screen.getByTestId("approval-card")).toBeInTheDocument();
    expect(screen.getByText(/get_identity_profile/)).toBeInTheDocument();
    expect(screen.getAllByText("DOE.Identity.sample-user")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: /approve workflow/i }));
    expect(onApprove).toHaveBeenCalledTimes(1);
  });
});
