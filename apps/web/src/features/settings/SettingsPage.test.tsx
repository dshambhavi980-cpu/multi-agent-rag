import { fireEvent, screen, waitFor } from "@testing-library/react";

import { renderWithProviders } from "../../test/render";
import { SettingsPage } from "./SettingsPage";

const mocks = vi.hoisted(() => ({
  requestJson: vi.fn(),
  update: vi.fn(),
  invalidateQueries: vi.fn(),
}));
vi.mock("../../api/client", () => ({ requestJson: mocks.requestJson }));
vi.mock("../auth/auth-context", () => ({
  useAuth: () => ({
    session: { access_token: "token" },
    user: { id: "user-123456789" },
  }),
}));
vi.mock("../workspaces/workspace-context", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "workspace-1", name: "Internal knowledge" },
  }),
}));
vi.mock("../../lib/supabase", () => ({
  supabase: {
    from: () => ({
      update: mocks.update,
    }),
  },
}));

beforeEach(() => {
  mocks.requestJson.mockReset();
  mocks.update.mockReset();
  mocks.requestJson.mockResolvedValue({
    documents: 4,
    document_bytes: 1048576,
    ready_documents: 3,
    conversations: 2,
    runs: 7,
    approvals: 1,
    memories: 5,
  });
  mocks.update.mockReturnValue({
    eq: vi.fn().mockResolvedValue({ error: null }),
  });
});

test("shows usage and renames the workspace", async () => {
  renderWithProviders(<SettingsPage />);
  expect(await screen.findByText("1.0 MB / 35 MB")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Workspace name"), {
    target: { value: "Operations" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => {
    expect(mocks.update).toHaveBeenCalledWith({ name: "Operations" });
  });
  expect(await screen.findByRole("button", { name: "Saved" })).toBeInTheDocument();
});

test("shows rename and usage failures", async () => {
  mocks.requestJson.mockRejectedValueOnce(new Error("offline"));
  mocks.update.mockReturnValue({
    eq: vi.fn().mockResolvedValue({ error: new Error("denied") }),
  });
  renderWithProviders(<SettingsPage />);
  expect(await screen.findByText(/Usage could not be loaded/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Workspace name"), {
    target: { value: "Operations" },
  });
  const form = screen.getByLabelText("Workspace name").closest("form");
  expect(form).not.toBeNull();
  fireEvent.submit(form as HTMLFormElement);
  expect(await screen.findByText(/could not be updated/)).toBeInTheDocument();
});
