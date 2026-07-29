export type Citation = {
  citation_id: string;
  document_id: string;
  chunk_id: string;
  label: string;
  page: number | null;
  section: string | null;
  quote: string;
  source_url: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  answer_status: "grounded" | "insufficient_evidence" | "failed" | null;
  confidence: number | null;
  citations: Citation[];
  created_at: string;
};

export type Conversation = {
  id: string;
  workspace_id: string;
  owner_id: string;
  title: string | null;
  summary: string | null;
  created_at: string;
  updated_at: string;
};

export type ConversationPage = { items: Conversation[]; next_cursor: string | null };
export type ConversationDetail = Conversation & { messages: Message[] };
export type RunAccepted = {
  run_id: string;
  message_id: string;
  status: string;
  events_url: string;
};
