import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../test/render";
import { App } from "./App";

const appMocks = vi.hoisted(() => ({
  selectWorkspace: vi.fn(),
}));

vi.mock("../features/auth/auth-context", () => ({
  useAuth: () => ({
    session: null,
    user: { id: "guest-1", is_anonymous: true },
    status: "authenticated",
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

test("selects a workspace and handles unknown routes in guest mode", async () => {
  const user = userEvent.setup();
  window.history.replaceState(null, "", "/unknown");
  renderWithProviders(<App />);

  expect(screen.getByRole("heading", { name: "Not found" })).toBeInTheDocument();
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Active workspace" }),
    "workspace-2",
  );

  expect(appMocks.selectWorkspace).toHaveBeenCalledWith("workspace-2");
  expect(screen.getByLabelText("Guest session")).toBeInTheDocument();
});
