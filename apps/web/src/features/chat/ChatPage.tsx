import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  ChevronRight,
  CircleAlert,
  FileText,
  History,
  LoaderCircle,
  MessageSquarePlus,
  Send,
  WifiOff,
  X,
} from "lucide-react";
import { type SyntheticEvent, useMemo, useState } from "react";

import {
  ApiClientError,
  requestJson,
  streamSse,
  type SseEvent,
} from "../../api/client";
import { SelectMenu } from "../../components/SelectMenu";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { useAuth } from "../auth/auth-context";
import type { DocumentPage } from "../documents/documents.types";
import { useWorkspace } from "../workspaces/workspace-context";
import { SourceViewer } from "./SourceViewer";
import type {
  Citation,
  Conversation,
  ConversationDetail,
  ConversationPage,
  Message,
  RunAccepted,
} from "./chat.types";

type Mode = "auto" | "simple" | "agentic";

function friendlyError(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.status === 429) return "This workspace is at its run limit. Wait a moment and retry.";
    if (error.status === 503) return "The free API is waking up. Retry in about thirty seconds.";
    if (error.status === 504) return "The answer exceeded its time limit. Try a narrower question.";
    return error.message;
  }
  return "The answer stream was interrupted. Your conversation is still saved.";
}

function AnswerContent({
  content,
  citations,
  onCitation,
}: {
  content: string;
  citations: Citation[];
  onCitation: (citation: Citation) => void;
}) {
  const citationMap = new Map(citations.map((citation) => [citation.citation_id, citation]));
  return (
    <p>
      {content.split(/(\[C[1-9][0-9]*\])/g).map((part, index) => {
        const id = part.match(/^\[(C[1-9][0-9]*)\]$/)?.[1];
        const citation = id ? citationMap.get(id) : undefined;
        return citation ? (
          <button
            className="inline-citation"
            type="button"
            key={`${citation.citation_id}-${String(index)}`}
            aria-label={`Open source ${citation.citation_id}: ${citation.label}`}
            onClick={() => {
              onCitation(citation);
            }}
          >
            {citation.citation_id}
          </button>
        ) : (
          <span key={`${part.slice(0, 12)}-${String(index)}`}>{part}</span>
        );
      })}
    </p>
  );
}

export function ChatPage() {
  const { session } = useAuth();
  const { activeWorkspace } = useWorkspace();
  const queryClient = useQueryClient();
  const online = useOnlineStatus();
  const workspaceId = activeWorkspace?.id;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<Mode>("auto");
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [streamed, setStreamed] = useState("");
  const [streamCitations, setStreamCitations] = useState<Citation[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [runState, setRunState] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<Citation | null>(null);
  const [conversationsOpen, setConversationsOpen] = useState(false);
  const awaitingReview = runState === "Awaiting human review";
  const headers = {
    Authorization: `Bearer ${session?.access_token ?? ""}`,
    "X-Workspace-ID": workspaceId ?? "",
  };

  const conversations = useQuery({
    queryKey: ["conversations", workspaceId],
    enabled: Boolean(session && workspaceId),
    queryFn: () =>
      requestJson<ConversationPage>("/v1/conversations", { headers }),
  });
  const activeId =
    selectedId === "new"
      ? null
      : (conversations.data?.items.find((item) => item.id === selectedId)?.id ??
        conversations.data?.items[0]?.id ??
        null);
  const detail = useQuery({
    queryKey: ["conversation", workspaceId, activeId],
    enabled: Boolean(session && workspaceId && activeId),
    queryFn: () =>
      requestJson<ConversationDetail>(`/v1/conversations/${activeId ?? ""}`, {
        headers,
      }),
  });
  const documents = useQuery({
    queryKey: ["documents", workspaceId],
    enabled: Boolean(session && workspaceId),
    queryFn: () => requestJson<DocumentPage>("/v1/documents", { headers }),
  });
  const readyDocuments = useMemo(
    () => documents.data?.items.filter((document) => document.status === "ready") ?? [],
    [documents.data?.items],
  );

  const resetDraft = () => {
    setSelectedId("new");
    setQuestion("");
    setStreamed("");
    setStreamCitations([]);
    setPendingQuestion(null);
    setRunState(null);
    setError(null);
  };

  const handleEvent = (event: SseEvent) => {
    if (event.event_type === "answer.delta" && typeof event.delta === "string") {
      const delta = event.delta;
      setStreamed((value) => value + delta);
    }
    if (event.event_type === "citations.available" && Array.isArray(event.citations)) {
      setStreamCitations(event.citations as Citation[]);
    }
    if (event.event_type === "agent.step_started" && typeof event.node === "string") {
      setRunState(`Agent: ${event.node}`);
    }
    if (event.event_type === "run.awaiting_approval") setRunState("Awaiting human review");
    if (event.event_type === "run.completed") setRunState("Completed");
    if (event.event_type === "run.failed") {
      setRunState("Failed");
      if (typeof event.detail === "string") setError(event.detail);
    }
  };

  const send = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = question.trim();
    if (!content || !session || !workspaceId || !online || sending || awaitingReview) return;
    setSending(true);
    setError(null);
    setStreamed("");
    setStreamCitations([]);
    setPendingQuestion(content);
    setRunState("Starting");
    setQuestion("");
    try {
      let conversationId = activeId;
      if (!conversationId || selectedId === "new") {
        const created = await requestJson<Conversation>("/v1/conversations", {
          method: "POST",
          headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
          body: JSON.stringify({ title: content.slice(0, 80) }),
        });
        conversationId = created.id;
        setSelectedId(created.id);
      }
      const accepted = await requestJson<RunAccepted>(
        `/v1/conversations/${conversationId}/messages`,
        {
          method: "POST",
          headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
          body: JSON.stringify({
            content,
            document_ids: selectedDocuments.length ? selectedDocuments : null,
            force_mode: mode,
          }),
        },
      );
      setRunState(accepted.status);
      await streamSse(accepted.events_url, { headers }, handleEvent);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] }),
        queryClient.invalidateQueries({
          queryKey: ["conversation", workspaceId, conversationId],
        }),
        queryClient.invalidateQueries({ queryKey: ["runs", workspaceId] }),
      ]);
      setPendingQuestion(null);
      setStreamed("");
      setStreamCitations([]);
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setSending(false);
    }
  };

  const messages: Message[] = detail.data?.messages ?? [];

  return (
    <section className="chat-page" aria-labelledby="chat-title">
      <h1 className="sr-only" id="chat-title">Chat</h1>
      <header className="chat-toolbar">
        <button
          className="chat-toolbar-button"
          type="button"
          aria-expanded={conversationsOpen}
          onClick={() => {
            setConversationsOpen(true);
          }}
        >
          <History size={18} /> Conversations
        </button>
        <span className="chat-title">
          {activeId
            ? (conversations.data?.items.find((item) => item.id === activeId)?.title ??
              "Untitled conversation")
            : "New conversation"}
        </span>
        <button className="chat-toolbar-button" type="button" onClick={resetDraft}>
          <MessageSquarePlus size={18} /> New chat
        </button>
      </header>

      {!online ? (
        <div className="inline-notice notice-warning" role="alert">
          <WifiOff size={18} />
          <span>You are offline. Existing messages remain available; sending is paused.</span>
        </div>
      ) : null}

      <div className="chat-workspace">
        <button
          className={`conversation-backdrop${conversationsOpen ? " is-open" : ""}`}
          type="button"
          aria-label="Close conversations"
          tabIndex={conversationsOpen ? 0 : -1}
          onClick={() => {
            setConversationsOpen(false);
          }}
        />
        <aside
          className={`conversation-drawer${conversationsOpen ? " is-open" : ""}`}
          aria-label="Conversations"
          aria-hidden={!conversationsOpen}
        >
          <div className="conversation-drawer-heading">
            <div>
              <strong>Conversations</strong>
              <span>Continue a previous thread</span>
            </div>
            <button
              className="icon-button"
              type="button"
              aria-label="Close conversations"
              onClick={() => {
                setConversationsOpen(false);
              }}
            >
              <X size={18} />
            </button>
          </div>
          <button
            className="conversation-new"
            type="button"
            onClick={() => {
              resetDraft();
              setConversationsOpen(false);
            }}
          >
            <MessageSquarePlus size={17} /> New conversation
          </button>
          <div className="conversation-list">
          {(conversations.data?.items ?? []).map((conversation) => (
            <button
              type="button"
              key={conversation.id}
              aria-current={activeId === conversation.id ? "true" : undefined}
              onClick={() => {
                setSelectedId(conversation.id);
                setPendingQuestion(null);
                setStreamed("");
                setError(null);
                setConversationsOpen(false);
              }}
            >
              <span>{conversation.title ?? "Untitled conversation"}</span>
              <ChevronRight size={15} />
            </button>
          ))}
          {conversations.isLoading ? <p>Loading conversations...</p> : null}
          {!conversations.isLoading && !conversations.data?.items.length ? (
            <p>No conversations yet.</p>
          ) : null}
          </div>
        </aside>

        <div className="chat-thread">
          <div className="message-scroll" aria-live="polite" aria-busy={sending}>
            {!messages.length && !pendingQuestion ? (
              <div className="chat-empty">
                <Bot size={26} />
                <h2>Ask from your indexed documents</h2>
                <p>Answers cite the exact source passages used.</p>
              </div>
            ) : null}
            {messages.map((message) => (
              <article className={`message message-${message.role}`} key={message.id}>
                <span className="message-role">
                  {message.role === "user" ? "You" : "DocPilot"}
                </span>
                {message.role === "assistant" ? (
                  <AnswerContent
                    content={message.content}
                    citations={message.citations}
                    onCitation={setSource}
                  />
                ) : (
                  <p>{message.content}</p>
                )}
                {message.confidence !== null ? (
                  <small>{Math.round(message.confidence * 100)}% confidence</small>
                ) : null}
              </article>
            ))}
            {pendingQuestion ? (
              <article className="message message-user">
                <span className="message-role">You</span>
                <p>{pendingQuestion}</p>
              </article>
            ) : null}
            {sending || streamed ? (
              <article className="message message-assistant message-streaming">
                <span className="message-role">
                  DocPilot {runState ? `- ${runState}` : ""}
                </span>
                {streamed ? (
                  <AnswerContent
                    content={streamed}
                    citations={streamCitations}
                    onCitation={setSource}
                  />
                ) : (
                  <p className="thinking-line">
                    <LoaderCircle className="spin" size={16} /> Retrieving evidence...
                  </p>
                )}
              </article>
            ) : null}
            {runState === "Awaiting human review" ? (
              <a className="review-link" href="/approvals">
                <CircleAlert size={16} /> Open the review queue
              </a>
            ) : null}
            {error ? (
              <div className="inline-notice notice-error" role="alert">
                <CircleAlert size={18} />
                <span>{error}</span>
              </div>
            ) : null}
          </div>

          <form className="chat-composer" onSubmit={(event) => void send(event)}>
            <div className="composer-input">
              <label className="sr-only" htmlFor="chat-question">Message DocPilot</label>
              <textarea
                id="chat-question"
                rows={2}
                maxLength={12000}
                value={question}
                disabled={awaitingReview}
                placeholder={
                  awaitingReview
                    ? "Complete the pending human review to continue"
                    : "Ask a question about your documents"
                }
                onChange={(event) => {
                  setQuestion(event.target.value);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
            </div>
            <div className="chat-options">
              <SelectMenu
                compact
                label="Run mode"
                value={mode}
                disabled={awaitingReview}
                onChange={setMode}
                options={[
                  {
                    value: "auto",
                    label: "Auto",
                    description: "Choose the best path",
                  },
                  {
                    value: "simple",
                    label: "Fast RAG",
                    description: "Direct grounded answer",
                  },
                  {
                    value: "agentic",
                    label: "Agentic",
                    description: "Plan and use tools",
                  },
                ]}
              />
              <details className="document-picker">
                <summary>
                  <FileText size={15} /> {selectedDocuments.length || "All"} sources
                </summary>
                <div>
                  {readyDocuments.map((document) => (
                    <label key={document.id}>
                      <input
                        type="checkbox"
                        checked={selectedDocuments.includes(document.id)}
                        onChange={(event) => {
                          setSelectedDocuments((current) =>
                            event.target.checked
                              ? [...current, document.id]
                              : current.filter((id) => id !== document.id),
                          );
                        }}
                      />
                      <span>{document.title ?? document.filename}</span>
                    </label>
                  ))}
                  {!readyDocuments.length ? <p>No indexed sources yet.</p> : null}
                </div>
              </details>
              <button
                className="send-button"
                type="submit"
                title="Send message"
                aria-label="Send message"
                disabled={!question.trim() || sending || !online || awaitingReview}
              >
                {sending ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}
              </button>
            </div>
          </form>
        </div>
      </div>

      {source && session && workspaceId ? (
        <SourceViewer
          citation={source}
          accessToken={session.access_token}
          workspaceId={workspaceId}
          onClose={() => {
            setSource(null);
          }}
        />
      ) : null}
    </section>
  );
}
