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
  Search01Icon,
  SendIcon,
  WifiDisconnected01Icon,
} from "@hugeicons/core-free-icons";
import {
  type ReactNode,
  type SyntheticEvent,
  useEffect,
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
import { ThoughtLine } from "../../components/ThoughtLine";
import PromptBar, {
  type PromptBarSendDetail,
  type PromptBarSource,
} from "../../components/PromptBar";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { useAuth } from "../auth/auth-context";
import { useTheme } from "../theme/theme-context";
import type { DocumentPage } from "../documents/documents.types";
import { useWorkspace } from "../workspaces/workspace-context";
import { SourceViewer } from "./SourceViewer";
import { formatAgentStep, formatConversationDisplay, normalizeMarkdownContent } from "./chat.utils";
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
  isStreaming,
}: {
  content: string;
  citations: Citation[];
  onCitation: (citation: Citation) => void;
  onImageClick?: (image: { src: string; alt?: string }) => void;
  isStreaming?: boolean;
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
      {isStreaming ? (
        <span className="streaming-cursor" aria-hidden="true">▋</span>
      ) : null}
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
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const queryClient = useQueryClient();
  const online = useOnlineStatus();
  const workspaceId = activeWorkspace?.id;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<Mode>("auto");
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [streamed, setStreamed] = useState("");
  const fullStreamedRef = useRef("");
  const displayedStreamedRef = useRef("");
  const streamIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastThoughtDurationRef = useRef<number>(1.8);
  const [thoughtsByMessageId, setThoughtsByMessageId] = useState<
    Map<string, { duration: number; steps: string[] }>
  >(new Map());
  const [conversationsOpen, setConversationsOpen] = useState(false);
  const [conversationSearch, setConversationSearch] = useState("");
  const [streamCitations, setStreamCitations] = useState<Citation[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [runState, setRunState] = useState<string | null>(null);
  const [agentSteps, setAgentSteps] = useState<string[]>([]);
  const agentStepsRef = useRef<string[]>([]);
  const completedAssistantMessageIdRef = useRef<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<Citation | null>(null);
  const [lightbox, setLightbox] = useState<{ src: string; alt?: string } | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const awaitingReview = runState === "Awaiting human review";

  const addAgentStep = (step: string) => {
    if (!agentStepsRef.current.includes(step)) {
      agentStepsRef.current = [...agentStepsRef.current, step];
      setAgentSteps(agentStepsRef.current);
    }
  };
  const headers = {
    Authorization: `Bearer ${session?.access_token ?? ""}`,
    "X-Workspace-ID": workspaceId ?? "",
  };

  useEffect(() => {
    if (!conversationsOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setConversationsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [conversationsOpen]);

  useEffect(() => {
    if (!sending) {
      if (streamIntervalRef.current) {
        clearInterval(streamIntervalRef.current);
        streamIntervalRef.current = null;
      }
      return;
    }

    if (!streamIntervalRef.current) {
      streamIntervalRef.current = setInterval(() => {
        const full = fullStreamedRef.current;
        const current = displayedStreamedRef.current;
        if (current.length < full.length) {
          const remaining = full.length - current.length;
          const step = Math.min(remaining, Math.max(2, Math.ceil(remaining / 5)));
          const next = full.slice(0, current.length + step);
          displayedStreamedRef.current = next;
          setStreamed(next);
        }
      }, 20);
    }

    return () => {
      if (streamIntervalRef.current) {
        clearInterval(streamIntervalRef.current);
        streamIntervalRef.current = null;
      }
    };
  }, [sending]);

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
  const filteredConversations = useMemo(() => {
    const items = conversations.data?.items ?? [];
    if (!conversationSearch.trim()) return items;
    const q = conversationSearch.toLowerCase().trim();
    return items.filter((item) =>
      (item.title ?? "Untitled conversation").toLowerCase().includes(q),
    );
  }, [conversations.data?.items, conversationSearch]);
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
    fullStreamedRef.current = "";
    displayedStreamedRef.current = "";
    setStreamCitations([]);
    setPendingQuestion(null);
    setRunState(null);
    agentStepsRef.current = [];
    setAgentSteps([]);
    setError(null);
  };

  const handleEvent = (event: SseEvent) => {
    if (event.event_type === "answer.delta" && typeof event.delta === "string") {
      const delta = event.delta;
      fullStreamedRef.current += delta;
      addAgentStep("Synthesis Agent: Generating grounded answer");
    }
    if (event.event_type === "citations.available" && Array.isArray(event.citations)) {
      setStreamCitations(event.citations as Citation[]);
      addAgentStep("Citation Verifier: Grounding claims with verified passages");
    }
    if (event.event_type === "agent.step_started" && typeof event.node === "string") {
      setRunState(`Agent: ${event.node}`);
      const step = formatAgentStep(event.node);
      addAgentStep(step);
    }
    if (event.event_type === "run.awaiting_approval") setRunState("Awaiting human review");
    if (event.event_type === "run.completed") {
      setRunState("Completed");
      if (typeof event.message_id === "string") {
        completedAssistantMessageIdRef.current = event.message_id;
      }
    }
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
    fullStreamedRef.current = "";
    displayedStreamedRef.current = "";
    setStreamCitations([]);
    setPendingQuestion(content);
    setRunState("Starting");
    agentStepsRef.current = [];
    completedAssistantMessageIdRef.current = null;
    setAgentSteps([]);
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

      // Drain remaining buffered stream smoothly so all words finish revealing
      while (displayedStreamedRef.current.length < fullStreamedRef.current.length) {
        await new Promise((r) => setTimeout(r, 25));
      }
      await new Promise((r) => setTimeout(r, 60));

      if (activeMode !== "simple" && agentStepsRef.current.length > 0) {
        const finalSteps = [...agentStepsRef.current];
        const duration = lastThoughtDurationRef.current || 1.8;
        setThoughtsByMessageId((prev) => {
          const next = new Map(prev);
          const thoughtData = {
            duration,
            steps: finalSteps,
          };
          if (completedAssistantMessageIdRef.current) {
            next.set(completedAssistantMessageIdRef.current, thoughtData);
          }
          next.set(accepted.message_id, thoughtData);
          return next;
        });
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] }),
        queryClient.invalidateQueries({
          queryKey: ["conversation", workspaceId, conversationId],
        }),
        queryClient.invalidateQueries({ queryKey: ["runs", workspaceId] }),
      ]);
      setPendingQuestion(null);
      setStreamed("");
      fullStreamedRef.current = "";
      displayedStreamedRef.current = "";
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
            void conversations.refetch();
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
        <div className="chat-thread">
          <div className="message-scroll" ref={scrollRef} aria-live="polite" aria-busy={sending}>
            {!messages.length && !pendingQuestion ? (
              <div className="chat-empty">
                <HugeiconsIcon icon={BotIcon} size={26} strokeWidth={1.8} />
                <h2>Ask from your indexed documents</h2>
                <p>Answers cite the exact source passages used.</p>
              </div>
            ) : null}
            {messages.map((message) => {
              const thought = thoughtsByMessageId.get(message.id);
              return (
                <article className={`message message-${message.role}`} key={message.id}>
                  {message.role === "user" ? (
                    <span className="message-role">You</span>
                  ) : null}
                  {message.role === "assistant" ? (
                    <>
                      {mode !== "simple" && thought && thought.steps.length > 0 ? (
                        <div className="agent-thinking-wrapper py-1">
                          <ThoughtLine
                            working={false}
                            steps={thought.steps}
                            label="Coordinating subagents…"
                            doneLabel="Thought for"
                            glyph="sparkle"
                            fontSize={13}
                            elapsed={thought.duration}
                            collapsible
                            collapseOnSettle={true}
                            showTimer
                          />
                        </div>
                      ) : null}
                      <AnswerContent
                        content={message.content}
                        citations={message.citations}
                        onCitation={setSource}
                        onImageClick={setLightbox}
                      />
                    </>
                  ) : (
                    <p>{message.content}</p>
                  )}
                  {message.confidence !== null ? (
                    <small>{Math.round(message.confidence * 100)}% confidence</small>
                  ) : null}
                </article>
              );
            })}
            {pendingQuestion ? (
              <article className="message message-user">
                <span className="message-role">You</span>
                <p>{pendingQuestion}</p>
              </article>
            ) : null}
            {sending || streamed ? (
              <article className="message message-assistant message-streaming">
                {mode !== "simple" ? (
                  <div className="agent-thinking-wrapper py-1">
                    <ThoughtLine
                      working={sending && !streamed}
                      steps={agentSteps}
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
                      onSettle={(sec) => {
                        lastThoughtDurationRef.current = sec;
                      }}
                    />
                  </div>
                ) : null}
                {streamed ? (
                  <AnswerContent
                    content={streamed}
                    citations={streamCitations}
                    onCitation={setSource}
                    onImageClick={setLightbox}
                    isStreaming={sending}
                  />
                ) : mode !== "simple" ? (
                  <p className="thinking-line">
                    <HugeiconsIcon icon={Loading03Icon} className="spin" size={16} strokeWidth={1.8} /> Retrieving evidence...
                  </p>
                ) : (
                  <div className="flex items-center gap-2 py-1.5 text-xs text-muted-foreground">
                    <HugeiconsIcon icon={Loading03Icon} className="spin" size={15} strokeWidth={2} />
                    <span>Generating answer...</span>
                  </div>
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

          <div className="docpilot-prompt-bar-wrap w-full flex justify-center py-2 bg-transparent border-0 shadow-none">
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
              background={isDark ? "#18181b" : "#ffffff"}
              color={isDark ? "#f4f4f5" : "#09090b"}
              menuBackground={isDark ? "#27272a" : "#ffffff"}
              sparkColor={isDark ? "#b39dff" : "#7c3aed"}
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

      {conversationsOpen ? (
        <div
          className="conversation-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="conversations-modal-title"
          onClick={() => setConversationsOpen(false)}
        >
          <div
            className="conversation-modal-card"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="conversation-modal-header">
              <div className="conversation-modal-title-wrap">
                <div className="flex items-center gap-2">
                  <HugeiconsIcon icon={Clock01Icon} size={18} strokeWidth={2} />
                  <h2 id="conversations-modal-title">Conversations</h2>
                </div>
                <p>Search and continue previous threads</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="conversation-modal-new-btn"
                  onClick={() => {
                    resetDraft();
                    setConversationsOpen(false);
                  }}
                >
                  <HugeiconsIcon icon={CommentAdd01Icon} size={14} strokeWidth={2} />
                  <span>New chat</span>
                </button>
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Close conversations"
                  onClick={() => setConversationsOpen(false)}
                >
                  <HugeiconsIcon icon={Cancel01Icon} size={18} strokeWidth={1.8} />
                </button>
              </div>
            </div>

            <div className="conversation-modal-search">
              <HugeiconsIcon icon={Search01Icon} size={16} strokeWidth={2} />
              <input
                type="text"
                className="conversation-search-input"
                placeholder="Search conversations by title..."
                value={conversationSearch}
                onChange={(e) => setConversationSearch(e.target.value)}
                autoFocus
              />
              {conversationSearch ? (
                <button
                  type="button"
                  className="conversation-search-clear"
                  onClick={() => setConversationSearch("")}
                  aria-label="Clear search"
                >
                  <HugeiconsIcon icon={Cancel01Icon} size={14} strokeWidth={2} />
                </button>
              ) : null}
            </div>

            <div className="conversation-modal-list">
              {filteredConversations.length > 0 ? (
                filteredConversations.map((conversation) => {
                  const isActive = activeId === conversation.id;
                  return (
                    <button
                      key={conversation.id}
                      type="button"
                      className={`conversation-modal-item ${isActive ? "active" : ""}`}
                      onClick={() => {
                        setSelectedId(conversation.id);
                        setPendingQuestion(null);
                        setStreamed("");
                        fullStreamedRef.current = "";
                        displayedStreamedRef.current = "";
                        setError(null);
                        setConversationsOpen(false);
                      }}
                    >
                      <div className="conversation-modal-item-content">
                        <div className="flex items-center gap-2">
                          <span className="conversation-modal-item-title">
                            {(() => {
                              const display = formatConversationDisplay(conversation.title);
                              return display.docName
                                ? `${display.title} — ${display.docName}`
                                : display.title;
                            })()}
                          </span>
                          {isActive ? (
                            <span className="conversation-modal-item-badge">Active</span>
                          ) : null}
                        </div>
                        <span className="conversation-modal-item-date">
                          {new Date(
                            conversation.updated_at || conversation.created_at,
                          ).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })}
                        </span>
                      </div>
                      <HugeiconsIcon
                        icon={ArrowRight01Icon}
                        size={16}
                        strokeWidth={2}
                        className="conversation-modal-item-arrow"
                      />
                    </button>
                  );
                })
              ) : conversations.isFetching ? (
                <div className="conversation-modal-empty">
                  <HugeiconsIcon
                    icon={Loading03Icon}
                    className="spin"
                    size={20}
                    strokeWidth={2}
                  />
                  <p>Loading conversations...</p>
                </div>
              ) : conversationSearch ? (
                <div className="conversation-modal-empty">
                  <p>No conversations matching &ldquo;{conversationSearch}&rdquo;</p>
                </div>
              ) : (
                <div className="conversation-modal-empty">
                  <p>No conversations yet. Start a new chat.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
