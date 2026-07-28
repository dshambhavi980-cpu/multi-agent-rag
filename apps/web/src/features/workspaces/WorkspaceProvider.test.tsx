import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";

import { WorkspaceProvider } from "./WorkspaceProvider";
import { useWorkspace } from "./workspace-context";

const mocks = vi.hoisted(() => ({
  rows: [
    {
      id: "workspace-1",
      name: "Knowledge",
      created_by: "user-1",
      created_at: "2026-07-28T00:00:00Z",
      updated_at: "2026-07-28T00:00:00Z",
    },
  ],
  queryError: null as Error | null,
  insertError: null as Error | null,
  from: vi.fn(),
  insert: vi.fn(),
}));

vi.mock("../auth/auth-context", () => ({
  useAuth: () => ({ user: { id: "user-1" } }),
}));

vi.mock("../../lib/supabase", () => ({
  supabase: {
    from: mocks.from,
  },
}));

function Wrapper({ children }: PropsWithChildren) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <WorkspaceProvider>{children}</WorkspaceProvider>
    </QueryClientProvider>
  );
}

function Consumer() {
  const workspace = useWorkspace();
  return (
    <>
      <p>{workspace.loading ? "loading" : "ready"}</p>
      <p>{workspace.activeWorkspace?.name ?? "none"}</p>
      <p>{workspace.error ?? "no error"}</p>
      <button
        type="button"
        onClick={() => {
          workspace.selectWorkspace("workspace-1");
        }}
      >
        Select
      </button>
      <button
        type="button"
        onClick={() => void workspace.createWorkspace(" New workspace ")}
      >
        Create
      </button>
    </>
  );
}

beforeEach(() => {
  vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
    "00000000-0000-4000-8000-000000000002",
  );
  window.localStorage.clear();
  mocks.queryError = null;
  mocks.insertError = null;
  mocks.from.mockReset();
  mocks.insert.mockReset();
  mocks.from.mockImplementation(() => ({
    select: () => ({
      order: () =>
        Promise.resolve({
          data: mocks.queryError ? null : mocks.rows,
          error: mocks.queryError,
        }),
      eq: () => ({
        single: () =>
          Promise.resolve({
            data: {
              id: "workspace-2",
              name: "New workspace",
              created_by: "user-1",
              created_at: "2026-07-28T00:00:00Z",
              updated_at: "2026-07-28T00:00:00Z",
            },
            error: mocks.insertError,
          }),
      }),
    }),
    insert: (payload: unknown) => {
      mocks.insert(payload);
      return Promise.resolve({ error: mocks.insertError });
    },
  }));
});

test("loads, selects, and creates workspaces", async () => {
  const user = userEvent.setup();
  render(<Consumer />, { wrapper: Wrapper });

  await waitFor(() => {
    expect(screen.getByText("Knowledge")).toBeInTheDocument();
  });
  await user.click(screen.getByRole("button", { name: "Select" }));
  expect(window.localStorage.getItem("docpilot.activeWorkspaceId")).toBe(
    "workspace-1",
  );

  await user.click(screen.getByRole("button", { name: "Create" }));
  await waitFor(() => {
    expect(mocks.insert).toHaveBeenCalledWith({
      id: "00000000-0000-4000-8000-000000000002",
      name: "New workspace",
      created_by: "user-1",
    });
  });
  expect(window.localStorage.getItem("docpilot.activeWorkspaceId")).toBe(
    "workspace-2",
  );
});

test("exposes workspace query errors", async () => {
  mocks.queryError = new Error("query failed");
  render(<Consumer />, { wrapper: Wrapper });

  await waitFor(() => {
    expect(screen.getByText("Workspaces could not be loaded.")).toBeInTheDocument();
  });
  expect(screen.getByText("none")).toBeInTheDocument();
});
