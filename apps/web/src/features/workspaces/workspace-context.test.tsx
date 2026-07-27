import { render, screen } from "@testing-library/react";

import {
  WorkspaceContext,
  type WorkspaceContextValue,
  useWorkspace,
} from "./workspace-context";

function Consumer() {
  return <p>{useWorkspace().activeWorkspace?.name ?? "none"}</p>;
}

test("provides the active workspace", () => {
  const value: WorkspaceContextValue = {
    workspaces: [],
    activeWorkspace: null,
    loading: false,
    error: null,
    creating: false,
    createWorkspace: vi.fn(),
    selectWorkspace: vi.fn(),
  };

  render(
    <WorkspaceContext.Provider value={value}>
      <Consumer />
    </WorkspaceContext.Provider>,
  );

  expect(screen.getByText("none")).toBeInTheDocument();
});

test("requires the workspace provider", () => {
  expect(() => render(<Consumer />)).toThrow(
    "useWorkspace must be used within WorkspaceProvider.",
  );
});
