import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { renderWithProviders } from "../../test/render";
import { ApprovalsPage } from "./ApprovalsPage";

const mocks = vi.hoisted(() => ({ requestJson: vi.fn() }));

vi.mock("../../api/client", () => ({ requestJson: mocks.requestJson }));
vi.mock("../auth/auth-context", () => ({
  useAuth: () => ({ session: { access_token: "token" }, status: "anonymous" }),
}));
vi.mock("../workspaces/workspace-context", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "workspace-1", name: "Guest workspace" },
  }),
}));

const item = {
  id: "approval-1",
  run_id: "70000000-0000-4000-8000-000000000001",
  status: "pending",
  risk_level: "high",
  reasons: ["The request contains a sensitive or external-action intent."],
  proposed_output: "A proposed cited answer. [C1]",
  reviewer_id: null,
  reviewer_comment: null,
  decided_at: null,
  created_at: "2026-07-29T00:00:00Z",
  updated_at: "2026-07-29T00:00:00Z",
};

beforeEach(() => {
  mocks.requestJson.mockReset();
  mocks.requestJson.mockResolvedValue({ items: [item], next_cursor: null });
});

test("loads a pending review and approves edited output with a comment", async () => {
  renderWithProviders(<ApprovalsPage />);

  expect(await screen.findByText("high risk")).toBeInTheDocument();
  expect(screen.getByText("Why review is required")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Proposed output"), {
    target: { value: "Reviewed output. [C1]" },
  });
  fireEvent.change(screen.getByLabelText("Reviewer comment"), {
    target: { value: "Evidence verified." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Approve" }));

  await waitFor(() => {
    expect(mocks.requestJson).toHaveBeenCalledWith(
      "/v1/approvals/approval-1/approve",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          comment: "Evidence verified.",
          edited_output: "Reviewed output. [C1]",
        }),
      }),
    );
  });
});

test("supports revision and renders empty and failed queues", async () => {
  const view = renderWithProviders(<ApprovalsPage />);
  await screen.findByText("high risk");
  fireEvent.change(screen.getByLabelText("Reviewer comment"), {
    target: { value: "Cover the exception." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Request revision" }));
  await waitFor(() => {
    expect(mocks.requestJson).toHaveBeenCalledWith(
      "/v1/approvals/approval-1/revise",
      expect.any(Object),
    );
  });
  view.unmount();

  mocks.requestJson.mockResolvedValueOnce({ items: [], next_cursor: null });
  const empty = renderWithProviders(<ApprovalsPage />);
  expect(await screen.findByText("No approval requests match this view.")).toBeInTheDocument();
  empty.unmount();

  mocks.requestJson.mockRejectedValue(new Error("offline"));
  renderWithProviders(<ApprovalsPage />);
  expect(
    await screen.findByText("The review queue could not be loaded."),
  ).toBeInTheDocument();
});
