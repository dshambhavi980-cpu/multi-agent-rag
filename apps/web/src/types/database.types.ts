export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export type Database = {
  __InternalSupabase: {
    PostgrestVersion: "14.5";
  };
  public: {
    Tables: {
      application_events: {
        Row: {
          actor_id: string | null;
          created_at: string;
          event_type: string;
          id: number;
          metadata: Json;
          request_id: string | null;
          target_id: string | null;
          target_type: string | null;
          workspace_id: string | null;
        };
        Insert: {
          actor_id?: string | null;
          created_at?: string;
          event_type: string;
          id?: never;
          metadata?: Json;
          request_id?: string | null;
          target_id?: string | null;
          target_type?: string | null;
          workspace_id?: string | null;
        };
        Update: never;
        Relationships: [];
      };
      documents: {
        Row: {
          chunk_count: number;
          content_type: string;
          created_at: string;
          failure_code: string | null;
          failure_detail: string | null;
          filename: string;
          id: string;
          index_version: number;
          target_index_version: number;
          chunk_strategy: string | null;
          embedding_model: string | null;
          embedding_dimensions: number | null;
          indexed_at: string | null;
          object_path: string;
          page_count: number | null;
          processing_version: number;
          sha256: string;
          size_bytes: number;
          status: Database["public"]["Enums"]["document_status"];
          tags: string[];
          title: string | null;
          updated_at: string;
          uploaded_by: string;
          workspace_id: string;
        };
        Insert: never;
        Update: never;
        Relationships: [];
      };
      ingestion_jobs: {
        Row: {
          attempt: number;
          completed_at: string | null;
          created_at: string;
          document_id: string;
          error_code: string | null;
          error_detail: string | null;
          id: string;
          locked_at: string | null;
          max_attempts: number;
          progress: number;
          queue_message_id: number | null;
          stage: string | null;
          status: Database["public"]["Enums"]["ingestion_job_status"];
          updated_at: string;
          workspace_id: string;
        };
        Insert: never;
        Update: never;
        Relationships: [];
      };
      profiles: {
        Row: {
          avatar_url: string | null;
          created_at: string;
          display_name: string | null;
          id: string;
          updated_at: string;
        };
        Insert: {
          avatar_url?: string | null;
          display_name?: string | null;
          id: string;
        };
        Update: {
          avatar_url?: string | null;
          display_name?: string | null;
        };
        Relationships: [];
      };
      workspace_members: {
        Row: {
          invited_by: string | null;
          joined_at: string;
          role: Database["public"]["Enums"]["workspace_role"];
          user_id: string;
          workspace_id: string;
        };
        Insert: {
          invited_by?: string | null;
          role?: Database["public"]["Enums"]["workspace_role"];
          user_id: string;
          workspace_id: string;
        };
        Update: {
          role?: Database["public"]["Enums"]["workspace_role"];
        };
        Relationships: [];
      };
      workspaces: {
        Row: {
          created_at: string;
          created_by: string;
          id: string;
          name: string;
          updated_at: string;
        };
        Insert: {
          created_by: string;
          id?: string;
          name: string;
        };
        Update: {
          name?: string;
        };
        Relationships: [];
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: {
      document_status:
        | "uploaded"
        | "queued"
        | "processing"
        | "ready"
        | "failed"
        | "quarantined";
      ingestion_job_status:
        | "queued"
        | "processing"
        | "completed"
        | "failed"
        | "quarantined";
      workspace_role: "owner" | "reviewer" | "member";
    };
    CompositeTypes: Record<string, never>;
  };
};

export type Workspace = Database["public"]["Tables"]["workspaces"]["Row"];
