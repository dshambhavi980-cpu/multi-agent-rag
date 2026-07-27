export type DocumentStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "ready"
  | "failed"
  | "quarantined";

export type WorkspaceDocument = {
  id: string;
  filename: string;
  title: string | null;
  content_type: string;
  size_bytes: number;
  status: DocumentStatus;
  index_version: number;
  target_index_version: number;
  chunk_strategy: "fixed" | "recursive" | "heading_recursive" | null;
  embedding_model: string | null;
  embedding_dimensions: number | null;
  indexed_at: string | null;
  page_count: number | null;
  chunk_count: number;
  failure_code: string | null;
  created_at: string;
};

export type DocumentPage = { items: WorkspaceDocument[]; next_cursor: string | null };

export type UploadUrl = {
  upload_id: string;
  object_path: string;
  signed_url: string;
  upload_token: string;
  expires_at: string;
};
