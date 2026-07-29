import { fireEvent, screen } from "@testing-library/react";

import { ApiClientError } from "../../api/client";
import { renderWithProviders } from "../../test/render";
import { EvaluationsPage } from "./EvaluationsPage";

const mocks = vi.hoisted(() => ({ requestJson: vi.fn() }));
vi.mock("../../api/client", () => {
  class MockApiClientError extends Error {
    constructor(
      message: string,
      readonly status: number,
    ) {
      super(message);
    }
  }
  return { ApiClientError: MockApiClientError, requestJson: mocks.requestJson };
});
vi.mock("../auth/auth-context", () => ({
  useAuth: () => ({ session: { access_token: "token" } }),
}));
vi.mock("../workspaces/workspace-context", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "workspace-1" } }),
}));

test("lists evaluation results and refreshes", async () => {
  mocks.requestJson.mockResolvedValue({
    items: [
      {
        id: "evaluation-1",
        suite: "golden-docs",
        variants: ["hybrid", "dense"],
        status: "completed",
        case_count: 25,
        created_at: "2026-07-29T00:00:00Z",
      },
    ],
    next_cursor: null,
  });
  renderWithProviders(<EvaluationsPage />);
  expect(await screen.findByText("golden-docs")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Refresh evaluations" }));
  expect(mocks.requestJson).toHaveBeenCalled();
});

test("distinguishes unavailable, failed, and empty evaluation states", async () => {
  mocks.requestJson.mockRejectedValueOnce(new ApiClientError("missing", 404));
  const unavailable = renderWithProviders(<EvaluationsPage />);
  expect(await screen.findByText(/not enabled/)).toBeInTheDocument();
  unavailable.unmount();

  mocks.requestJson.mockRejectedValueOnce(new Error("offline"));
  const failed = renderWithProviders(<EvaluationsPage />);
  expect(await screen.findByText(/could not be loaded/)).toBeInTheDocument();
  failed.unmount();

  mocks.requestJson.mockResolvedValueOnce({ items: [], next_cursor: null });
  renderWithProviders(<EvaluationsPage />);
  expect(await screen.findByText(/No evaluation runs/)).toBeInTheDocument();
});
