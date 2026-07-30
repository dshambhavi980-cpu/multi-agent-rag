import { fireEvent, screen, waitFor } from "@testing-library/react";

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

  fireEvent.change(screen.getByLabelText("Message DocPilot"), {
    target: { value: "How should I rotate it?" },
  });
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
