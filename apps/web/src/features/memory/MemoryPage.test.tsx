import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { renderWithProviders } from "../../test/render";
import { MemoryPage } from "./MemoryPage";

const mocks = vi.hoisted(() => ({
  requestJson: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  requestJson: mocks.requestJson,
}));

vi.mock("../auth/auth-context", () => ({
  useAuth: () => ({
    session: { access_token: "token" },
    user: { id: "user-1" },
    status: "anonymous",
  }),
}));

vi.mock("../workspaces/workspace-context", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "workspace-1", name: "Guest workspace" },
  }),
}));

const item = {
  id: "memory-1",
  workspace_id: "workspace-1",
  owner_id: "user-1",
  conversation_id: "conversation-1",
  source_message_id: "message-1",
  content: "I prefer concise answers.",
  source_type: "explicit_user",
  source_excerpt: "Remember that I prefer concise answers.",
  confidence: 1,
  visibility: "private",
  expires_at: null,
  created_at: "2026-07-29T00:00:00Z",
  updated_at: "2026-07-29T00:00:00Z",
  can_delete: true,
};

beforeEach(() => {
  mocks.requestJson.mockReset();
  mocks.requestJson.mockResolvedValue({ items: [item], next_cursor: null });
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

test("shows provenance, filters visibility, and deletes owned memory", async () => {
  renderWithProviders(<MemoryPage />);

  expect(await screen.findByText("I prefer concise answers.")).toBeInTheDocument();
  expect(screen.getByText("100% confidence")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Provenance"));
  expect(screen.getByText("Remember that I prefer concise answers.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Private" }));
  await waitFor(() => {
    expect(mocks.requestJson).toHaveBeenCalledWith(
      "/v1/memories?visibility=private",
      expect.any(Object),
    );
  });
  await screen.findByText("I prefer concise answers.");

  fireEvent.click(
    screen.getByRole("button", { name: "Delete memory: I prefer concise answers." }),
  );
  await waitFor(() => {
    expect(mocks.requestJson).toHaveBeenCalledWith(
      "/v1/memories/memory-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});

test("renders empty and failed states", async () => {
  mocks.requestJson.mockResolvedValueOnce({ items: [], next_cursor: null });
  const empty = renderWithProviders(<MemoryPage />);
  expect(await screen.findByText("No active memories match this view.")).toBeInTheDocument();
  empty.unmount();

  mocks.requestJson.mockRejectedValue(new Error("offline"));
  renderWithProviders(<MemoryPage />);
  expect(await screen.findByText("Memory could not be loaded.")).toBeInTheDocument();
});

test("shows shared approved memory as read only", async () => {
  mocks.requestJson.mockResolvedValueOnce({
    items: [
      {
        ...item,
        visibility: "workspace",
        source_type: "approved",
        expires_at: "2026-08-29T00:00:00Z",
        can_delete: false,
      },
    ],
    next_cursor: null,
  });
  renderWithProviders(<MemoryPage />);

  expect(await screen.findByText("Human approved")).toBeInTheDocument();
  expect(screen.getByText("workspace")).toBeInTheDocument();
  expect(screen.queryByLabelText(/Delete memory/)).not.toBeInTheDocument();
  expect(screen.getByText(/^Expires /)).toBeInTheDocument();
});
