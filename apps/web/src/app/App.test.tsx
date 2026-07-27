import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../test/render";
import { App } from "./App";

const appMocks = vi.hoisted(() => ({
  signOut: vi.fn(),
  selectWorkspace: vi.fn(),
}));

vi.mock("../features/auth/auth-context", () => ({
  useAuth: () => ({
    session: null,
    user: { email: "pat@example.test" },
    status: "authenticated",
    signInWithEmail: vi.fn(),
    signOut: appMocks.signOut,
  }),
}));

vi.mock("../features/workspaces/workspace-context", () => ({
  useWorkspace: () => ({
    workspaces: [
      {
        id: "workspace-1",
        name: "Internal knowledge",
        created_by: "user-1",
        created_at: "2026-07-28T00:00:00Z",
        updated_at: "2026-07-28T00:00:00Z",
      },
      {
        id: "workspace-2",
        name: "Customer success",
        created_by: "user-1",
        created_at: "2026-07-28T00:00:00Z",
        updated_at: "2026-07-28T00:00:00Z",
      },
    ],
    activeWorkspace: {
      id: "workspace-1",
      name: "Internal knowledge",
      created_by: "user-1",
      created_at: "2026-07-28T00:00:00Z",
      updated_at: "2026-07-28T00:00:00Z",
    },
    loading: false,
    error: null,
    creating: false,
    createWorkspace: vi.fn(),
    selectWorkspace: appMocks.selectWorkspace,
  }),
}));

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  appMocks.signOut.mockReset();
  appMocks.selectWorkspace.mockReset();
});

vi.mock("../features/system/SystemOverview", () => ({
  SystemOverview: () => <h1>System overview</h1>,
}));

test("navigates between operational sections", async () => {
  const user = userEvent.setup();
  renderWithProviders(<App />);

  expect(screen.getByRole("heading", { name: "System overview" })).toBeInTheDocument();

  await user.click(screen.getByRole("link", { name: "Documents" }));

  expect(screen.getByRole("heading", { name: "Documents" })).toBeInTheDocument();
});

test("opens and closes mobile navigation", async () => {
  const user = userEvent.setup();
  renderWithProviders(<App />);

  await user.click(screen.getByRole("button", { name: "Open navigation" }));
  expect(screen.getByRole("navigation", { name: "Primary navigation" }).parentElement).toHaveClass(
    "sidebar-open",
  );

  await user.click(screen.getByRole("button", { name: "Close navigation" }));
  expect(screen.getByRole("navigation", { name: "Primary navigation" }).parentElement).not.toHaveClass(
    "sidebar-open",
  );
});

test("selects a workspace, signs out, and handles unknown routes", async () => {
  const user = userEvent.setup();
  window.history.replaceState(null, "", "/unknown");
  renderWithProviders(<App />);

  expect(screen.getByRole("heading", { name: "Not found" })).toBeInTheDocument();
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Active workspace" }),
    "workspace-2",
  );
  await user.click(screen.getByRole("button", { name: "Sign out" }));

  expect(appMocks.selectWorkspace).toHaveBeenCalledWith("workspace-2");
  expect(appMocks.signOut).toHaveBeenCalled();
});
