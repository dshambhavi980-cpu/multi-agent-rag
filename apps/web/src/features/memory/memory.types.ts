export type MemoryVisibility = "private" | "workspace";

export type MemoryItem = {
  id: string;
  workspace_id: string;
  owner_id: string;
  conversation_id: string | null;
  source_message_id: string | null;
  content: string;
  source_type: "explicit_user" | "approved";
  source_excerpt: string;
  confidence: number;
  visibility: MemoryVisibility;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
  can_delete: boolean;
};

export type MemoryPageResult = {
  items: MemoryItem[];
  next_cursor: string | null;
};
