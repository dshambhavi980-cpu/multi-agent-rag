import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/render";
import { DocumentsPage } from "./DocumentsPage";

const mocks = vi.hoisted(() => ({
  requestJson: vi.fn(),
  upload: vi.fn(),
  removeChannel: vi.fn(),
  refetch: vi.fn(),
}));

vi.mock("../../api/client", () => ({ requestJson: mocks.requestJson }));
vi.mock("../auth/auth-context", () => ({
  useAuth: () => ({
    session: { access_token: "access-token" },
  }),
}));
vi.mock("../workspaces/workspace-context", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "workspace-1" } }),
}));
vi.mock("../../lib/supabase", () => {
  const channel = {
    on: vi.fn().mockReturnThis(),
    subscribe: vi.fn().mockReturnThis(),
  };
  return {
    supabase: {
      channel: vi.fn(() => channel),
      removeChannel: mocks.removeChannel,
      storage: {
        from: vi.fn(() => ({ uploadToSignedUrl: mocks.upload })),
      },
    },
  };
});

const documentPage = {
  items: [
    {
      id: "document-1",
      filename: "guide.md",
      title: null,
      content_type: "text/markdown",
      size_bytes: 2048,
      status: "ready",
      index_version: 1,
      target_index_version: 1,
      chunk_strategy: "heading_recursive",
      embedding_model: "gemini-embedding-001",
      embedding_dimensions: 768,
      indexed_at: "2026-07-28T00:00:00Z",
      page_count: 2,
      chunk_count: 3,
      failure_code: null,
      created_at: "2026-07-28T00:00:00Z",
    },
  ],
  next_cursor: null,
};

beforeEach(() => {
  mocks.requestJson.mockReset();
  mocks.upload.mockReset();
  mocks.removeChannel.mockReset();
  mocks.requestJson.mockImplementation((path: string) => {
    if (path === "/v1/documents/upload-url") {
      return Promise.resolve({
        upload_id: "upload-1",
        object_path: "workspace-1/user/upload-1/notes.md",
        signed_url: "https://signed",
        upload_token: "upload-token",
        expires_at: "2026-07-28T01:00:00Z",
      });
    }
    if (path === "/v1/documents/complete-upload") {
      return Promise.resolve({ accepted: true });
    }
    return Promise.resolve(documentPage);
  });
  mocks.upload.mockResolvedValue({ error: null });
  vi.spyOn(globalThis.crypto.subtle, "digest").mockResolvedValue(
    new Uint8Array(32).buffer,
  );
});

test("lists, refreshes, and uploads a supported document", async () => {
  const user = userEvent.setup();
  renderWithProviders(<DocumentsPage />);

  expect(await screen.findByText("guide.md")).toBeInTheDocument();
  expect(screen.getByText("2.0 KB")).toBeInTheDocument();
  expect(screen.getByText("v1 · heading recursive")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Refresh documents" }));

  const input = document.querySelector("input[type=file]");
  expect(input).not.toBeNull();
  const file = new File(["hello"], "notes.md", { type: "text/markdown" });
  Object.defineProperty(file, "arrayBuffer", {
    value: () => Promise.resolve(new Uint8Array([1, 2, 3]).buffer),
  });
  await user.upload(input as HTMLInputElement, file);

  await waitFor(() => {
    expect(mocks.upload).toHaveBeenCalled();
  });
  expect(mocks.requestJson).toHaveBeenCalledWith(
    "/v1/documents/complete-upload",
    expect.objectContaining({ method: "POST" }),
  );
  expect(
    screen.getByText("Upload verified and queued for ingestion."),
  ).toBeInTheDocument();
});

test("accepts drag and drop and reports unsupported files", async () => {
  renderWithProviders(<DocumentsPage />);
  await screen.findByText("guide.md");
  const zone = screen.getByText("Add source documents").closest(".upload-zone");
  expect(zone).not.toBeNull();

  fireEvent.dragOver(zone as Element);
  fireEvent.drop(zone as Element, {
    dataTransfer: { files: [new File(["x"], "image.png", { type: "image/png" })] },
  });

  expect(
    await screen.findByText("Choose a PDF, TXT, Markdown, or HTML file."),
  ).toBeInTheDocument();
});

test("renders empty and failed query states", async () => {
  mocks.requestJson.mockResolvedValueOnce({ items: [], next_cursor: null });
  const first = renderWithProviders(<DocumentsPage />);
  expect(
    await screen.findByText("No documents in this workspace yet."),
  ).toBeInTheDocument();
  first.unmount();

  mocks.requestJson.mockRejectedValue(new Error("offline"));
  renderWithProviders(<DocumentsPage />);
  expect(
    await screen.findByText("Documents could not be loaded."),
  ).toBeInTheDocument();
});
