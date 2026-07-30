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
  window.localStorage.clear();
  Object.defineProperty(window, "innerWidth", { value: 1024, writable: true });
  appMocks.selectWorkspace.mockReset();
});

vi.mock("../features/system/SystemOverview", () => ({
  SystemOverview: () => <h1>System overview</h1>,
}));

vi.mock("../features/observability/ObservabilityPage", () => ({
  ObservabilityPage: () => <h1>Operations</h1>,
}));

test("lazy-loads every operational section", async () => {
  const user = userEvent.setup();
  renderWithProviders(<App />);

  expect(screen.getByRole("heading", { name: "System overview" })).toBeInTheDocument();

  for (const name of [
    "Chat",
    "Documents",
    "Agent runs",
    "Operations",
    "Review queue",
    "Evaluations",
    "Memory",
    "Settings",
  ]) {
    await user.click(screen.getByRole("link", { name }));
    expect(
      await screen.findByRole("heading", { name }, { timeout: 5_000 }),
    ).toBeInTheDocument();
  }
}, 30_000);

test("opens and closes mobile navigation", async () => {
  const user = userEvent.setup();
  Object.defineProperty(window, "innerWidth", { value: 500, writable: true });
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
  await user.click(screen.getByRole("button", { name: "Active workspace" }));
  await user.click(screen.getByRole("option", { name: "Customer success" }));

  expect(appMocks.selectWorkspace).toHaveBeenCalledWith("workspace-2");
  expect(screen.getByLabelText("Guest session")).toBeInTheDocument();
});

test("collapses and restores desktop navigation", async () => {
  const user = userEvent.setup();
  renderWithProviders(<App />);

  await user.click(screen.getByRole("button", { name: "Collapse navigation" }));
  expect(screen.getByRole("navigation", { name: "Primary navigation" }).parentElement).toHaveClass(
    "sidebar-hidden",
  );
  await user.click(screen.getByRole("button", { name: "Open navigation" }));
  expect(screen.getByRole("navigation", { name: "Primary navigation" }).parentElement).not.toHaveClass(
    "sidebar-hidden",
  );
});
