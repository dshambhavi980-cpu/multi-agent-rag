import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Database,
  LockKeyhole,
  RefreshCw,
  Trash2,
  Users,
} from "lucide-react";
import { useState } from "react";

import { requestJson } from "../../api/client";
import { useAuth } from "../auth/auth-context";
import { useWorkspace } from "../workspaces/workspace-context";
import type {
  MemoryPageResult,
  MemoryVisibility,
} from "./memory.types";

type VisibilityFilter = "all" | MemoryVisibility;

function formatSource(source: "explicit_user" | "approved"): string {
  return source === "explicit_user" ? "Explicit request" : "Human approved";
}

export function MemoryPage() {
  const { session } = useAuth();
  const { activeWorkspace } = useWorkspace();
  const queryClient = useQueryClient();
  const [visibility, setVisibility] = useState<VisibilityFilter>("all");
  const workspaceId = activeWorkspace?.id;
  const queryKey = ["memory", workspaceId, visibility];
  const headers = {
    Authorization: `Bearer ${session?.access_token ?? ""}`,
    "X-Workspace-ID": workspaceId ?? "",
  };

  const memories = useQuery({
    queryKey,
    enabled: Boolean(session && workspaceId),
    queryFn: () => {
      const query = visibility === "all" ? "" : `?visibility=${visibility}`;
      return requestJson<MemoryPageResult>(`/v1/memories${query}`, { headers });
    },
  });

  const remove = useMutation({
    mutationFn: (memoryId: string) =>
      requestJson<{ id: string; deleted: boolean }>(`/v1/memories/${memoryId}`, {
        method: "DELETE",
        headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["memory", workspaceId] });
    },
  });

  return (
    <section aria-labelledby="memory-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Context controls</p>
          <h1 id="memory-title">Memory</h1>
        </div>
        <button
          className="icon-button bordered"
          type="button"
          title="Refresh memory"
          aria-label="Refresh memory"
          onClick={() => void memories.refetch()}
        >
          <RefreshCw size={18} />
        </button>
      </div>

      <div className="memory-toolbar">
        <div className="segmented-control" aria-label="Memory visibility">
          {(["all", "private", "workspace"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={visibility === option}
              onClick={() => {
                setVisibility(option);
              }}
            >
              {option === "all" ? "All" : option === "private" ? "Private" : "Workspace"}
            </button>
          ))}
        </div>
        <span className="memory-count">
          {memories.data?.items.length ?? 0} active
        </span>
      </div>

      <div className="memory-list">
        {(memories.data?.items ?? []).map((memory) => (
          <article className="memory-row" key={memory.id}>
            <div className="memory-scope" title={`${memory.visibility} memory`}>
              {memory.visibility === "private" ? (
                <LockKeyhole size={18} aria-hidden="true" />
              ) : (
                <Users size={18} aria-hidden="true" />
              )}
            </div>
            <div className="memory-content">
              <p>{memory.content}</p>
              <div className="memory-meta">
                <span>{formatSource(memory.source_type)}</span>
                <span>{Math.round(memory.confidence * 100)}% confidence</span>
                <span>{memory.visibility}</span>
                <span>
                  {memory.expires_at
                    ? `Expires ${new Date(memory.expires_at).toLocaleDateString()}`
                    : "No expiry"}
                </span>
              </div>
              <details>
                <summary>Provenance</summary>
                <p>{memory.source_excerpt}</p>
              </details>
            </div>
            {memory.can_delete ? (
              <button
                className="icon-button memory-delete"
                type="button"
                title="Delete memory"
                aria-label={`Delete memory: ${memory.content}`}
                disabled={remove.isPending}
                onClick={() => {
                  if (window.confirm("Delete this remembered information?")) {
                    remove.mutate(memory.id);
                  }
                }}
              >
                <Trash2 size={17} />
              </button>
            ) : null}
          </article>
        ))}
        {memories.isLoading ? <p className="table-message">Loading memory...</p> : null}
        {memories.isError ? (
          <p className="table-message">Memory could not be loaded.</p>
        ) : null}
        {!memories.isLoading && !memories.data?.items.length ? (
          <div className="memory-empty">
            <Database size={25} aria-hidden="true" />
            <p>No active memories match this view.</p>
          </div>
        ) : null}
      </div>
      {remove.isError ? (
        <p className="form-message form-error" role="alert">
          The memory could not be deleted.
        </p>
      ) : null}
    </section>
  );
}
