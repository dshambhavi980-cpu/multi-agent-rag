import { useQuery, useQueryClient } from "@tanstack/react-query";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  Alert01Icon,
  ArrowRight01Icon,
  BotIcon,
  Cancel01Icon,
  Clock01Icon,
  CommentAdd01Icon,
  File02Icon,
  Loading03Icon,
  SendIcon,
  WifiDisconnected01Icon,
} from "@hugeicons/core-free-icons";
import {
  type ReactNode,
  type SyntheticEvent,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

import {
  ApiClientError,
  requestJson,
  streamSse,
  type SseEvent,
} from "../../api/client";
import { SelectMenu } from "../../components/SelectMenu";
import { SourceMenu } from "../../components/SourceMenu";
import { Thinking } from "../../components/Thinking";
import { ThoughtLine } from "../../components/ThoughtLine";
import PromptBar, {
  type PromptBarSendDetail,
  type PromptBarSource,
} from "../../components/PromptBar";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { useAuth } from "../auth/auth-context";
import type { DocumentPage } from "../documents/documents.types";
import { useWorkspace } from "../workspaces/workspace-context";
import { SourceViewer } from "./SourceViewer";
import { formatAgentStep, normalizeMarkdownContent } from "./chat.utils";
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
  onImageClick,
}: {
  content: string;
  citations: Citation[];
  onCitation: (citation: Citation) => void;
  onImageClick?: (image: { src: string; alt?: string }) => void;
}) {
  const citationMap = new Map(citations.map((citation) => [citation.citation_id, citation]));
  const markdown = normalizeMarkdownContent(content);
  return (
    <div className="message-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        urlTransform={(url) =>
          url.startsWith("citation:") ? url : defaultUrlTransform(url)
        }
        components={{
          img: ({ src, alt }) => {
            if (!src) return null;
            return (
              <span className="chat-figure" role="figure">
                <img
                  src={src}
                  alt={alt ?? "Architecture diagram"}
                  className="chat-embedded-image"
                  loading="lazy"
                  onClick={() => onImageClick?.(alt ? { src, alt } : { src })}
                />
                {alt ? <span className="chat-figure-caption">{alt}</span> : null}
              </span>
            );
          },
          a: ({ href, children }) => {
            const citationId = href?.startsWith("citation:")
              ? href.slice("citation:".length)
              : null;
            const citation = citationId ? citationMap.get(citationId) : undefined;
            return citation ? (
              <button
                className="inline-citation"
                type="button"
                aria-label={`Open source ${citation.citation_id}: ${citation.label}`}
                onClick={() => {
                  onCitation(citation);
                }}
              >
                {citation.citation_id}
              </button>
            ) : (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

function TopbarPortal({
  targetId,
  children,
}: {
  targetId: string;
  children: ReactNode;
}) {
  const [target, setTarget] = useState<HTMLElement | null>(() =>
    typeof document !== "undefined" ? document.getElementById(targetId) : null,
  );

  useLayoutEffect(() => {
    if (!target && typeof document !== "undefined") {
      const el = document.getElementById(targetId);
      if (el) {
        queueMicrotask(() => {
          setTarget(el);
        });
      }
    }
  }, [targetId, target]);

  if (!target) {
    return <div className="chat-toolbar-fallback">{children}</div>;
  }

  return createPortal(children, target);
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
  const [agentSteps, setAgentSteps] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<Citation | null>(null);
  const [lightbox, setLightbox] = useState<{ src: string; alt?: string } | null>(null);
  const [conversationsOpen, setConversationsOpen] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const awaitingReview = runState === "Awaiting human review";
  const headers = {
    Authorization: `Bearer ${session?.access_token ?? ""}`,
    "X-Workspace-ID": workspaceId ?? "",
  };

  useLayoutEffect(() => {
    const composer = composerRef.current;
    if (!composer) return;
    composer.style.height = "auto";
    const height = Math.min(composer.scrollHeight, 176);
    composer.style.height = `${String(height)}px`;
    composer.style.overflowY = composer.scrollHeight > 176 ? "auto" : "hidden";
  }, [question]);

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
    setAgentSteps([]);
    setError(null);
  };

  const handleEvent = (event: SseEvent) => {
    if (event.event_type === "answer.delta" && typeof event.delta === "string") {
      const delta = event.delta;
      setStreamed((value) => value + delta);
      setAgentSteps((steps) => {
        const step = "Synthesis Agent: Generating grounded answer";
        return steps.includes(step) ? steps : [...steps, step];
      });
    }
    if (event.event_type === "citations.available" && Array.isArray(event.citations)) {
      setStreamCitations(event.citations as Citation[]);
      setAgentSteps((steps) => {
        const step = "Citation Verifier: Grounding claims with verified passages";
        return steps.includes(step) ? steps : [...steps, step];
      });
    }
    if (event.event_type === "agent.step_started" && typeof event.node === "string") {
      setRunState(`Agent: ${event.node}`);
      const step = formatAgentStep(event.node);
      setAgentSteps((steps) => (steps.includes(step) ? steps : [...steps, step]));
    }
    if (event.event_type === "run.awaiting_approval") setRunState("Awaiting human review");
    if (event.event_type === "run.completed") setRunState("Completed");
    if (event.event_type === "run.failed") {
      setRunState("Failed");
      if (typeof event.detail === "string") setError(event.detail);
    }
  };

  const send = async (
    event?: SyntheticEvent<HTMLFormElement>,
    customText?: string,
    detail?: PromptBarSendDetail,
  ) => {
    if (event) event.preventDefault();
    const content = (customText ?? question).trim();
    if (!content || !session || !workspaceId || !online || sending || awaitingReview) return;
    const activeMode = (detail?.model?.key as Mode | undefined) ?? mode;
    setSending(true);
    setError(null);
    setStreamed("");
    setStreamCitations([]);
    setPendingQuestion(content);
    setRunState("Starting");
    setAgentSteps([
      "Query Analyzer: Decomposing request and extracting intents",
      "Router Agent: Deploying subagents for document search",
    ]);
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
            force_mode: activeMode,
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

  interface SpeechRecognitionResultItem {
    transcript?: string;
  }
  interface SpeechRecognitionResultList {
    [index: number]: {
      [index: number]: SpeechRecognitionResultItem | undefined;
    } | undefined;
  }
  interface SpeechRecognitionEvent {
    results?: SpeechRecognitionResultList;
  }
  interface SpeechRecognitionInstance {
    continuous: boolean;
    interimResults: boolean;
    lang: string;
    onresult: ((event: SpeechRecognitionEvent) => void) | null;
    onerror: (() => void) | null;
    onend: (() => void) | null;
    start: () => void;
  }
  interface SpeechRecognitionConstructor {
    new (): SpeechRecognitionInstance;
  }

  const handleDictate = (): Promise<string> => {
    return new Promise((resolve) => {
      const speechWindow = window as unknown as {
        SpeechRecognition?: SpeechRecognitionConstructor;
        webkitSpeechRecognition?: SpeechRecognitionConstructor;
      };
      const SpeechRec = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
      if (!SpeechRec) {
        alert("Voice dictation is supported in Chrome, Edge, and Safari.");
        resolve("");
        return;
      }
      try {
        const rec = new SpeechRec();
        rec.continuous = false;
        rec.interimResults = false;
        rec.lang = "en-US";
        rec.onresult = (e: SpeechRecognitionEvent) => {
          const t = e.results?.[0]?.[0]?.transcript ?? "";
          resolve(t);
        };
        rec.onerror = () => {
          resolve("");
        };
        rec.onend = () => {
          resolve("");
        };
        rec.start();
      } catch {
        resolve("");
      }
    });
  };

  const promptSources = useMemo<PromptBarSource[]>(() => {
    return [
      {
        key: "all",
        name: "All Documents",
        description: "Search across all indexed workspace documents",
        icon: File02Icon as PromptBarSource["icon"],
      },
      ...readyDocuments.map((doc) => ({
        key: doc.id,
        name: doc.title ?? doc.filename,
        description: `${doc.content_type} • Page search`,
        icon: File02Icon as PromptBarSource["icon"],
      })),
    ];
  }, [readyDocuments]);

  const messages: Message[] = useMemo(
    () => detail.data?.messages ?? [],
    [detail.data?.messages],
  );

  useLayoutEffect(() => {
    const scrollContainer = scrollRef.current;
    if (!scrollContainer) return;
    scrollContainer.scrollTop = scrollContainer.scrollHeight;
  }, [messages, streamed, pendingQuestion, runState]);

  return (
    <section className="chat-page" aria-labelledby="chat-title">
      <h1 className="sr-only" id="chat-title">Chat</h1>
      <TopbarPortal targetId="topbar-chat-left">
        <button
          className="chat-toolbar-button"
          type="button"
          aria-expanded={conversationsOpen}
          onClick={() => {
            setConversationsOpen(true);
          }}
        >
          <HugeiconsIcon icon={Clock01Icon} size={18} strokeWidth={1.8} />
          <span>Conversations</span>
        </button>
      </TopbarPortal>

      <TopbarPortal targetId="topbar-chat-center">
        <span
          className="chat-title"
          title={
            activeId
              ? (conversations.data?.items.find((item) => item.id === activeId)?.title ??
                "Untitled conversation")
              : "New conversation"
          }
        >
          {activeId
            ? (conversations.data?.items.find((item) => item.id === activeId)?.title ??
              "Untitled conversation")
            : "New conversation"}
        </span>
      </TopbarPortal>

      <TopbarPortal targetId="topbar-chat-right">
        <button className="chat-toolbar-button" type="button" onClick={resetDraft}>
          <HugeiconsIcon icon={CommentAdd01Icon} size={18} strokeWidth={1.8} />
          <span>New chat</span>
        </button>
      </TopbarPortal>

      {!online ? (
        <div className="inline-notice notice-warning" role="alert">
          <HugeiconsIcon icon={WifiDisconnected01Icon} size={18} strokeWidth={1.8} />
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
              <HugeiconsIcon icon={Cancel01Icon} size={18} strokeWidth={1.8} />
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
            <HugeiconsIcon icon={CommentAdd01Icon} size={17} strokeWidth={1.8} /> New conversation
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
              <HugeiconsIcon icon={ArrowRight01Icon} size={15} strokeWidth={1.8} />
            </button>
          ))}
          {conversations.isLoading ? <p>Loading conversations...</p> : null}
          {!conversations.isLoading && !conversations.data?.items.length ? (
            <p>No conversations yet.</p>
          ) : null}
          </div>
        </aside>

        <div className="chat-thread">
          <div className="message-scroll" ref={scrollRef} aria-live="polite" aria-busy={sending}>
            {!messages.length && !pendingQuestion ? (
              <div className="chat-empty">
                <HugeiconsIcon icon={BotIcon} size={26} strokeWidth={1.8} />
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
                    onImageClick={setLightbox}
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
                  DocPilot
                  {runState && !["accepted", "starting"].includes(runState.toLowerCase())
                    ? ` - ${runState}`
                    : ""}
                </span>
                <div className="agent-thinking-wrapper py-2">
                  <div className="flex items-center gap-2 mb-2 text-zinc-300">
                    <Thinking />
                  </div>
                  <ThoughtLine
                    working={sending && !streamed}
                    steps={
                      agentSteps.length
                        ? agentSteps
                        : [
                            "Query Analyzer: Decomposing request and extracting intents",
                            "Router Agent: Deploying subagents for document search",
                            "Retrieval Agent: Slicing document pages and fetching vector matches",
                            "Citation Verifier: Grounding claims with original PDF coordinates",
                            "Synthesis Agent: Generating multimodal response",
                          ]
                    }
                    label="Coordinating subagents…"
                    doneLabel="Thought for"
                    glyph="sparkle"
                    fontSize={13}
                    breathPeriod={1.6}
                    breathDepth={0.45}
                    settleDuration={350}
                    settleBlur={2}
                    collapsible
                    collapseOnSettle={Boolean(streamed)}
                    showTimer
                  />
                </div>
                {streamed ? (
                  <AnswerContent
                    content={streamed}
                    citations={streamCitations}
                    onCitation={setSource}
                    onImageClick={setLightbox}
                  />
                ) : (
                  <p className="thinking-line">
                    <HugeiconsIcon icon={Loading03Icon} className="spin" size={16} strokeWidth={1.8} /> Retrieving evidence...
                  </p>
                )}
              </article>
            ) : null}
            {runState === "Awaiting human review" ? (
              <a className="review-link" href="/approvals">
                <HugeiconsIcon icon={Alert01Icon} size={16} strokeWidth={1.8} /> Open the review queue
              </a>
            ) : null}
            {error ? (
              <div className="inline-notice notice-error" role="alert">
                <HugeiconsIcon icon={Alert01Icon} size={18} strokeWidth={1.8} />
                <span>{error}</span>
              </div>
            ) : null}
          </div>

          <div className="docpilot-prompt-bar-wrap w-full flex justify-center py-2">
            <PromptBar
              placeholder={
                awaitingReview
                  ? "Complete pending human review to continue"
                  : "Ask anything about your documents..."
              }
              sources={promptSources}
              commands={[
                { key: "summarize", name: "/summarize", description: "Summarize this system design" },
                { key: "compare", name: "/compare", description: "Compare architecture approaches" },
                { key: "explain", name: "/explain", description: "Explain system components step by step" },
              ]}
              models={[
                { key: "simple", name: "Fast RAG", tag: "Direct" },
                { key: "agentic", name: "Agentic RAG", tag: "Multi-Agent" },
                { key: "auto", name: "Auto", tag: "Best Path" },
              ]}
              defaultModel={mode}
              efforts={[]}
              busy={sending}
              onSend={(text, detail) => {
                if (detail.model?.key) {
                  setMode(detail.model.key as Mode);
                }
                void send(undefined, text, detail);
              }}
              onDictate={handleDictate}
              background="#18181b"
              color="#f4f4f5"
              menuBackground="#27272a"
              sparkColor="#b39dff"
              width={760}
              radius={16}
              className="w-full max-w-3xl"
            />
          </div>

          <form className="chat-composer-hidden sr-only" onSubmit={(event) => void send(event)}>
            <div className="composer-input">
              <label className="sr-only" htmlFor="chat-question">Message DocPilot</label>
              <textarea
                id="chat-question"
                ref={composerRef}
                rows={1}
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
              <SourceMenu
                options={readyDocuments.map((document) => ({
                  id: document.id,
                  label: document.title ?? document.filename,
                }))}
                selected={selectedDocuments}
                disabled={awaitingReview}
                onChange={setSelectedDocuments}
              />
              <button
                className="send-button"
                type="submit"
                title="Send message"
                aria-label="Send message"
                disabled={!question.trim() || sending || !online || awaitingReview}
              >
                {sending ? (
                  <HugeiconsIcon icon={Loading03Icon} className="spin" size={18} strokeWidth={1.8} />
                ) : (
                  <HugeiconsIcon icon={SendIcon} size={18} strokeWidth={1.8} />
                )}
              </button>
            </div>
          </form>
        </div>
      </div>

      {source && session && workspaceId ? (
        <SourceViewer
          key={`${source.document_id}:${source.page ? String(source.page) : "document"}`}
          citation={source}
          accessToken={session.access_token}
          workspaceId={workspaceId}
          onClose={() => {
            setSource(null);
          }}
        />
      ) : null}

      {lightbox ? (
        <div
          className="chat-lightbox-overlay"
          role="dialog"
          aria-label="Enlarged diagram"
          onClick={() => {
            setLightbox(null);
          }}
        >
          <div
            className="chat-lightbox-content"
            onClick={(e) => {
              e.stopPropagation();
            }}
          >
            <img src={lightbox.src} alt={lightbox.alt ?? "Diagram"} />
            {lightbox.alt ? <p className="chat-lightbox-caption">{lightbox.alt}</p> : null}
            <button
              type="button"
              className="chat-lightbox-close"
              onClick={() => {
                setLightbox(null);
              }}
              aria-label="Close image preview"
            >
              <HugeiconsIcon icon={Cancel01Icon} size={18} strokeWidth={1.8} />
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
