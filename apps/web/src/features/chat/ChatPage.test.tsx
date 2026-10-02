import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { ApiClientError } from "../../api/client";
import { renderWithProviders } from "../../test/render";
import { ChatPage } from "./ChatPage";

const mocks = vi.hoisted(() => ({
  requestJson: vi.fn(),
  streamSse: vi.fn(),
  online: true,
}));

vi.mock("../../api/client", () => {
  class MockApiClientError extends Error {
    constructor(
      message: string,
      readonly status: number,
    ) {
      super(message);
    }
  }
  return {
    API_BASE_URL: "/api",
    ApiClientError: MockApiClientError,
    requestJson: mocks.requestJson,
    streamSse: mocks.streamSse,
  };
});
vi.mock("../../hooks/useOnlineStatus", () => ({
  useOnlineStatus: () => mocks.online,
}));
vi.mock("../auth/auth-context", () => ({
  useAuth: () => ({ session: { access_token: "token" } }),
}));
vi.mock("../workspaces/workspace-context", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "workspace-1" } }),
}));

const conversation = {
  id: "conversation-1",
  workspace_id: "workspace-1",
  owner_id: "user-1",
  title: "Emergency access",
  summary: null,
  created_at: "2026-07-29T00:00:00Z",
  updated_at: "2026-07-29T00:00:00Z",
};
const citation = {
  citation_id: "C1",
  document_id: "document-1",
  chunk_id: "chunk-1",
  label: "Operations",
  page: 2,
  section: "Reset",
  quote: "Rotate the emergency token.",
  source_url: "/v1/documents/document-1/source?page=2",
};

beforeEach(() => {
  mocks.online = true;
  mocks.requestJson.mockReset();
  mocks.streamSse.mockReset();
  mocks.requestJson.mockImplementation((path: string, options?: RequestInit) => {
    if (path === "/v1/conversations" && options?.method === "POST") {
      return Promise.resolve({ ...conversation, id: "conversation-2" });
    }
    if (path === "/v1/conversations") {
      return Promise.resolve({ items: [conversation], next_cursor: null });
    }
    if (path === "/v1/conversations/conversation-1") {
      return Promise.resolve({
        ...conversation,
        messages: [
          {
            id: "message-1",
            conversation_id: conversation.id,
            role: "assistant",
            content:
              "* **Step 1:** Rotate it [C1]. * **Step 2:** Record the audit event [C1].",
            answer_status: "grounded",
            confidence: 0.91,
            citations: [citation],
            created_at: conversation.created_at,
          },
        ],
      });
    }
    if (path === "/v1/documents") {
      return Promise.resolve({
        items: [
          {
            id: "document-1",
            filename: "operations.md",
            title: "Operations",
            status: "ready",
          },
        ],
      });
    }
    if (path.includes("/messages")) {
      return Promise.resolve({
        run_id: "run-1",
        message_id: "message-2",
        status: "accepted",
        events_url: "/v1/runs/run-1/events",
      });
    }
    return Promise.resolve({});
  });
  mocks.streamSse.mockImplementation(
    (_path: string, _options: RequestInit, onEvent: (event: object) => void) => {
      onEvent({ event_type: "agent.step_started", sequence: 1, node: "retrieve" });
      onEvent({ event_type: "answer.delta", sequence: 2, delta: "Grounded " });
      onEvent({ event_type: "citations.available", sequence: 3, citations: [citation] });
      onEvent({ event_type: "run.completed", sequence: 4 });
      return Promise.resolve();
    },
  );
});

test("renders cited history and streams a new message", async () => {
  renderWithProviders(<ChatPage />);

  expect(
    await screen.findByText(
      (_content, element) =>
        element?.tagName === "LI" &&
        element.textContent === "Step 1: Rotate it C1.",
    ),
  ).toBeInTheDocument();
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  const [firstCitation] = screen.getAllByRole("button", { name: /Open source C1/ });
  if (!firstCitation) throw new Error("Expected at least one citation");
  fireEvent.click(firstCitation);
  expect(await screen.findByRole("dialog", { name: "Operations" })).toBeInTheDocument();
  fireEvent.keyDown(window, { key: "Escape" });

  const composer = screen.getByLabelText("Message DocPilot");
  expect(composer).toHaveAttribute("rows", "1");
  Object.defineProperty(composer, "scrollHeight", { configurable: true, value: 88 });
  fireEvent.change(composer, {
    target: { value: "How should I rotate it?" },
  });
  expect(composer.style.height).toBe("88px");
  Object.defineProperty(composer, "scrollHeight", { configurable: true, value: 220 });
  fireEvent.change(composer, {
    target: { value: "How should I rotate it, record it, and verify the audit event?" },
  });
  expect(composer.style.height).toBe("176px");
  expect(composer.style.overflowY).toBe("auto");
  fireEvent.click(screen.getByRole("button", { name: "Run mode" }));
  fireEvent.click(screen.getByRole("option", { name: /Agentic/ }));
  const sendButton = screen.getByRole("button", { name: "Send message" });
  expect(sendButton.parentElement).toHaveClass("chat-options");
  fireEvent.click(sendButton);

  await waitFor(() => {
    expect(mocks.streamSse).toHaveBeenCalledWith(
      "/v1/runs/run-1/events",
      expect.any(Object),
      expect.any(Function),
    );
  });
});

test("creates a conversation and explains offline and cold-start failures", async () => {
  const view = renderWithProviders(<ChatPage />);
  await screen.findAllByText("Emergency access");
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  fireEvent.change(screen.getByLabelText("Message DocPilot"), {
    target: { value: "A new question" },
  });
  mocks.streamSse.mockRejectedValueOnce(
    new ApiClientError("Service unavailable", 503),
  );
  const form = screen.getByLabelText("Message DocPilot").closest("form");
  expect(form).not.toBeNull();
  fireEvent.submit(form as HTMLFormElement);
  expect(await screen.findByText(/free API is waking up/)).toBeInTheDocument();
  expect(mocks.requestJson).toHaveBeenCalledWith(
    "/v1/conversations",
    expect.objectContaining({ method: "POST" }),
  );

  view.unmount();
  mocks.online = false;
  renderWithProviders(<ChatPage />);
  expect(screen.getByText(/You are offline/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
});

test("locks the composer while an agent run awaits human review", async () => {
  mocks.streamSse.mockImplementationOnce(
    (_path: string, _options: RequestInit, onEvent: (event: object) => void) => {
      onEvent({ event_type: "run.awaiting_approval", sequence: 1 });
      return Promise.resolve();
    },
  );
  renderWithProviders(<ChatPage />);
  await screen.findAllByText("Emergency access");
  fireEvent.change(screen.getByLabelText("Message DocPilot"), {
    target: { value: "Prepare a production deployment decision" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));

  expect(await screen.findByRole("link", { name: /Open the review queue/ })).toBeVisible();
  expect(screen.getByLabelText("Message DocPilot")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Run mode" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  expect(
    mocks.requestJson.mock.calls.filter(([path]) => String(path).endsWith("/messages")),
  ).toHaveLength(1);
});

test.each([
  [new ApiClientError("limited", 429), /workspace is at its run limit/],
  [new ApiClientError("timeout", 504), /exceeded its time limit/],
  [new ApiClientError("Provider rejected the request.", 422), /Provider rejected/],
  [new Error("connection reset"), /answer stream was interrupted/],
])("maps stream failures to useful recovery messages", async (failure, expected) => {
  mocks.streamSse.mockRejectedValueOnce(failure);
  renderWithProviders(<ChatPage />);
  await screen.findAllByText("Emergency access");
  fireEvent.change(screen.getByLabelText("Message DocPilot"), {
    target: { value: "Explain the policy" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByText(expected)).toBeInTheDocument();
});

test("renders embedded diagram images and opens lightbox preview", async () => {
  mocks.requestJson.mockImplementation((path: string) => {
    if (path === "/v1/conversations") {
      return Promise.resolve({ items: [conversation] });
    }
    if (path === "/v1/conversations/conversation-1") {
      return Promise.resolve({
        conversation,
        messages: [
          {
            id: "msg-diagram",
            conversation_id: "conversation-1",
            role: "assistant",
            content:
              "Here is the diagram:\n\n![Token Bucket Architecture](https://example.com/token_bucket.png)\n\nIt works via refill [C1].",
            citations: [citation],
            confidence: 0.95,
            created_at: "2026-07-29T00:00:00Z",
          },
        ],
      });
    }
    if (path === "/v1/documents") {
      return Promise.resolve({ items: [] });
    }
    return Promise.resolve({});
  });

  renderWithProviders(<ChatPage />);
  const img = await screen.findByAltText("Token Bucket Architecture");
  expect(img).toBeInTheDocument();
  fireEvent.click(img);
  const overlay = screen.getByRole("dialog", { name: "Enlarged diagram" });
  expect(overlay).toBeInTheDocument();
  fireEvent.click(overlay);
  expect(screen.queryByRole("dialog", { name: "Enlarged diagram" })).not.toBeInTheDocument();

  const hiddenInput = screen.getByPlaceholderText("Ask a question about your documents");
  fireEvent.change(hiddenInput, { target: { value: "Tell me about load balancers" } });
  fireEvent.keyDown(hiddenInput, { key: "Enter", shiftKey: true });
  fireEvent.keyDown(hiddenInput, { key: "Enter", shiftKey: false });
});

test("auto-heals broken markdown image tags from document-assets", async () => {
  mocks.requestJson.mockImplementation((path: string) => {
    if (path === "/v1/conversations") {
      return Promise.resolve({ items: [conversation] });
    }
    if (path === "/v1/conversations/conversation-1") {
      return Promise.resolve({
        conversation,
        messages: [
          {
            id: "msg-healed",
            conversation_id: "conversation-1",
            role: "assistant",
            content:
              "In this](https://example.supabase.co/storage/v1/object/public/document-assets/alex/fig_p56_1.jpeg) [C1]",
            citations: [citation],
            confidence: 0.95,
            created_at: "2026-07-29T00:00:00Z",
          },
        ],
      });
    }
    if (path === "/v1/documents") {
      return Promise.resolve({ items: [] });
    }
    return Promise.resolve({});
  });

  renderWithProviders(<ChatPage />);
  const img = await screen.findByAltText("Architecture Diagram");
  expect(img).toBeInTheDocument();
  expect(img).toHaveAttribute(
    "src",
    "https://example.supabase.co/storage/v1/object/public/document-assets/alex/fig_p56_1.jpeg",
  );
});

test("sends message via prompt bar with selected mode", async () => {
  renderWithProviders(<ChatPage />);
  await screen.findAllByText("Emergency access");

  const promptInput = screen.getByRole("textbox", { name: "Prompt" });
  fireEvent.change(promptInput, { target: { value: "Tell me about distributed caching." } });

  const sendBtn = screen.getByRole("button", { name: "Send" });
  fireEvent.click(sendBtn);

  await waitFor(() => {
    expect(mocks.requestJson).toHaveBeenCalledWith(
      expect.stringContaining("/messages"),
      expect.objectContaining({
        method: "POST",
      }),
    );
  });
});

test("supports dictation and sending with custom model detail", async () => {
  renderWithProviders(<ChatPage />);
  await screen.findAllByText("Emergency access");

  const micBtn = screen.getByRole("button", { name: "Dictate" });
  fireEvent.click(micBtn);

  const promptInput = screen.getByRole("textbox", { name: "Prompt" });
  fireEvent.change(promptInput, { target: { value: "Tell me about distributed caching." } });

  const modelBtn = screen.getByRole("button", { name: "Choose model" });
  fireEvent.click(modelBtn);
  const agenticOption = screen.getByRole("option", { name: /Agentic RAG/ });
  fireEvent.click(agenticOption);

  const sendBtn = screen.getByRole("button", { name: "Send" });
  fireEvent.click(sendBtn);

  await waitFor(() => {
    expect(mocks.requestJson).toHaveBeenCalledWith(
      expect.stringContaining("/messages"),
      expect.objectContaining({
        method: "POST",
      }),
    );
  });
});

test("opens conversation search modal, filters items, and selects a thread", async () => {
  renderWithProviders(<ChatPage />);
  await screen.findAllByText("Emergency access");

  const convBtn = screen.getByRole("button", { name: "Conversations" });
  fireEvent.click(convBtn);

  const modal = await screen.findByRole("dialog", { name: "Conversations" });
  expect(modal).toBeInTheDocument();

  const searchInput = within(modal).getByPlaceholderText("Search conversations by title...");
  fireEvent.change(searchInput, { target: { value: "Emergency" } });
  expect(within(modal).getByText("Emergency access")).toBeInTheDocument();

  const clearBtn = within(modal).getByRole("button", { name: "Clear search" });
  fireEvent.click(clearBtn);
  expect(searchInput).toHaveValue("");

  fireEvent.change(searchInput, { target: { value: "Non-existent thread query" } });
  expect(within(modal).getByText(/No conversations matching/)).toBeInTheDocument();

  fireEvent.change(searchInput, { target: { value: "" } });
  const itemBtn = within(modal).getByRole("button", { name: /Emergency access/ });
  fireEvent.click(itemBtn);
  expect(screen.queryByRole("dialog", { name: "Conversations" })).not.toBeInTheDocument();

  fireEvent.click(convBtn);
  expect(await screen.findByRole("dialog", { name: "Conversations" })).toBeInTheDocument();
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("dialog", { name: "Conversations" })).not.toBeInTheDocument();

  fireEvent.click(convBtn);
  const activeModal = await screen.findByRole("dialog", { name: "Conversations" });
  const newChatInModal = within(activeModal).getByRole("button", { name: "New chat" });
  fireEvent.click(newChatInModal);
  expect(screen.queryByRole("dialog", { name: "Conversations" })).not.toBeInTheDocument();
});

