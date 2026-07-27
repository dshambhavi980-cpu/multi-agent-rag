import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { WorkspaceContextValue } from "./workspace-context";
import { WorkspaceGate } from "./WorkspaceGate";

const state = vi.hoisted(() => ({
  workspace: null as WorkspaceContextValue | null,
}));

vi.mock("./workspace-context", () => ({
  useWorkspace: () => state.workspace,
}));

function workspaceValue(
  overrides: Partial<WorkspaceContextValue> = {},
): WorkspaceContextValue {
  return {
    workspaces: [],
    activeWorkspace: null,
    loading: false,
    error: null,
    creating: false,
    createWorkspace: vi.fn(),
    selectWorkspace: vi.fn(),
    ...overrides,
  };
}

test("shows loading and renders content for an active workspace", () => {
  state.workspace = workspaceValue({ loading: true });
  const view = render(
    <WorkspaceGate>
      <p>Workspace content</p>
    </WorkspaceGate>,
  );
  expect(screen.getByText("Loading your workspaces")).toBeInTheDocument();

  state.workspace = workspaceValue({
    activeWorkspace: {
      id: "workspace-1",
      name: "Knowledge",
      created_by: "user-1",
      created_at: "2026-07-28T00:00:00Z",
      updated_at: "2026-07-28T00:00:00Z",
    },
  });
  view.rerender(
    <WorkspaceGate>
      <p>Workspace content</p>
    </WorkspaceGate>,
  );
  expect(screen.getByText("Workspace content")).toBeInTheDocument();
});

test("creates the first workspace", async () => {
  const user = userEvent.setup();
  const createWorkspace = vi.fn().mockResolvedValue(undefined);
  state.workspace = workspaceValue({ createWorkspace });
  render(
    <WorkspaceGate>
      <p>Workspace content</p>
    </WorkspaceGate>,
  );

  await user.type(screen.getByLabelText("Workspace name"), "Research");
  await user.click(screen.getByRole("button", { name: "Create workspace" }));

  expect(createWorkspace).toHaveBeenCalledWith("Research");
});

test("reports loading and creation errors", async () => {
  const user = userEvent.setup();
  state.workspace = workspaceValue({
    error: "Workspaces could not be loaded.",
    createWorkspace: vi.fn().mockRejectedValue(new Error("insert failed")),
  });
  render(
    <WorkspaceGate>
      <p>Workspace content</p>
    </WorkspaceGate>,
  );

  expect(screen.getByRole("alert")).toHaveTextContent(
    "Workspaces could not be loaded.",
  );
  await user.type(screen.getByLabelText("Workspace name"), "Research");
  await user.click(screen.getByRole("button", { name: "Create workspace" }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Workspaces could not be loaded.",
  );
});
