import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { FileCheck2, FileUp, LoaderCircle, RefreshCw, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { requestJson } from "../../api/client";
import { supabase } from "../../lib/supabase";
import { useAuth } from "../auth/auth-context";
import { useWorkspace } from "../workspaces/workspace-context";
import type { DocumentPage, UploadUrl } from "./documents.types";

const contentTypes: Record<string, string> = {
  pdf: "application/pdf",
  txt: "text/plain",
  md: "text/markdown",
  markdown: "text/markdown",
  html: "text/html",
  htm: "text/html",
};

function formatBytes(size: number): string {
  if (size < 1024) return `${String(size)} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatStrategy(strategy: string | null): string {
  return strategy ? strategy.replaceAll("_", " ") : "Pending";
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export function DocumentsPage() {
  const { session } = useAuth();
  const { activeWorkspace } = useWorkspace();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const workspaceId = activeWorkspace?.id;
  const queryKey = ["documents", workspaceId];

  const documents = useQuery({
    queryKey,
    enabled: Boolean(session && workspaceId),
    queryFn: () =>
      requestJson<DocumentPage>("/v1/documents", {
        headers: {
          Authorization: `Bearer ${session?.access_token ?? ""}`,
          "X-Workspace-ID": workspaceId ?? "",
        },
      }),
    refetchInterval: (query) =>
      query.state.data?.items.some((item) =>
        ["uploaded", "queued", "processing"].includes(item.status),
      )
        ? 2_000
        : false,
  });
  const documentItems = documents.data?.items ?? [];
  // React Compiler intentionally leaves TanStack Virtual's imperative API alone.
  // eslint-disable-next-line react-hooks/incompatible-library
  const documentVirtualizer = useVirtualizer({
    count: documentItems.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => 54,
    overscan: 8,
    initialRect: { width: 800, height: 480 },
  });
  const measuredRows = documentVirtualizer.getVirtualItems();
  const documentRows = measuredRows.length
    ? measuredRows
    : documentItems.slice(0, 20).map((document, index) => ({
        index,
        key: document.id,
        start: index * 54,
      }));

  useEffect(() => {
    if (!supabase || !workspaceId) return;
    const client = supabase;
    const refresh = () => void queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
    const channel = client
      .channel(`documents:${workspaceId}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "documents", filter: `workspace_id=eq.${workspaceId}` },
        refresh,
      )
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "ingestion_jobs",
          filter: `workspace_id=eq.${workspaceId}`,
        },
        refresh,
      )
      .subscribe();
    return () => {
      void client.removeChannel(channel);
    };
  }, [queryClient, workspaceId]);

  const upload = async (file: File) => {
    if (!supabase || !session || !workspaceId) return;
    setMessage(null);
    setUploading(true);
    try {
      const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
      const contentType = contentTypes[extension];
      if (!contentType) throw new Error("Choose a PDF, TXT, Markdown, or HTML file.");
      if (file.size > 25 * 1024 * 1024) throw new Error("Files must be 25 MB or smaller.");
      const checksum = await sha256(file);
      const headers = {
        Authorization: `Bearer ${session.access_token}`,
        "X-Workspace-ID": workspaceId,
      };
      const signed = await requestJson<UploadUrl>("/v1/documents/upload-url", {
        method: "POST",
        headers,
        body: JSON.stringify({
          filename: file.name,
          content_type: contentType,
          size_bytes: file.size,
          sha256: checksum,
        }),
      });
      const { error } = await supabase.storage
        .from("workspace-documents")
        .uploadToSignedUrl(signed.object_path, signed.upload_token, file, {
          contentType,
          upsert: false,
        });
      if (error) {
        throw new Error("The document could not be uploaded. Please try again.");
      }
      await requestJson("/v1/documents/complete-upload", {
        method: "POST",
        headers,
        body: JSON.stringify({
          upload_id: signed.upload_id,
          object_path: signed.object_path,
          sha256: checksum,
        }),
      });
      setMessage("Upload verified and queued for ingestion.");
      await queryClient.invalidateQueries({ queryKey });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <section aria-labelledby="documents-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Knowledge base</p>
          <h1 id="documents-title">Documents</h1>
        </div>
        <button
          className="icon-button bordered"
          type="button"
          title="Refresh documents"
          aria-label="Refresh documents"
          onClick={() => void documents.refetch()}
        >
          <RefreshCw size={18} />
        </button>
      </div>

      <div
        className="upload-zone"
        onDragOver={(event) => {
          event.preventDefault();
        }}
        onDrop={(event) => {
          event.preventDefault();
          const file = event.dataTransfer.files[0];
          if (file) void upload(file);
        }}
      >
        {uploading ? <LoaderCircle className="spin" size={27} /> : <UploadCloud size={27} />}
        <div>
          <strong>{uploading ? "Verifying and uploading" : "Add source documents"}</strong>
          <p>PDF, TXT, Markdown, or HTML, up to 25 MB</p>
        </div>
        <button
          className="primary-button upload-button"
          type="button"
          disabled={uploading}
          onClick={() => input.current?.click()}
        >
          <FileUp size={17} />
          Upload
        </button>
        <input
          ref={input}
          className="sr-only"
          type="file"
          accept=".pdf,.txt,.md,.markdown,.html,.htm"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
          }}
        />
      </div>
      {message ? <p className="upload-message" role="status">{message}</p> : null}

      <div className="document-table-wrap" ref={listRef}>
        <table className="document-table">
          <thead>
            <tr>
              <th>Name</th><th>Status</th><th>Index</th><th>Size</th>
              <th>Pages</th><th>Added</th>
            </tr>
          </thead>
          <tbody
            className="document-virtual-body"
            style={{ height: `${String(documentVirtualizer.getTotalSize())}px` }}
          >
            {documentRows.map((virtualItem) => {
              const document = documentItems[virtualItem.index];
              if (!document) return null;
              return (
              <tr
                key={document.id}
                style={{ transform: `translateY(${String(virtualItem.start)}px)` }}
              >
                <td>
                  <span className="document-name">
                    <FileCheck2 size={17} />
                    <span>{document.title ?? document.filename}</span>
                  </span>
                </td>
                <td><span className={`document-status status-${document.status}`}>{document.status}</span></td>
                <td>
                  <span className="index-version">
                    v{document.index_version} · {formatStrategy(document.chunk_strategy)}
                  </span>
                </td>
                <td>{formatBytes(document.size_bytes)}</td>
                <td>{document.page_count ?? "-"}</td>
                <td>{new Date(document.created_at).toLocaleDateString()}</td>
              </tr>
              );
            })}
          </tbody>
        </table>
        {documents.isLoading ? <p className="table-message">Loading documents...</p> : null}
        {documents.isError ? (
          <div className="table-message">
            <p>Documents could not be loaded.</p>
            <button className="secondary-button" type="button" onClick={() => void documents.refetch()}>
              <RefreshCw size={16} /> Retry
            </button>
          </div>
        ) : null}
        {!documents.isLoading && !documents.data?.items.length ? (
          <p className="table-message">No documents in this workspace yet.</p>
        ) : null}
      </div>
    </section>
  );
}
