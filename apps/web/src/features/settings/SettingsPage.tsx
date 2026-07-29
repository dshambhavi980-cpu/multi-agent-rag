import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Database,
  FileStack,
  Gauge,
  MessageSquareText,
  Save,
  ShieldCheck,
} from "lucide-react";
import { type SyntheticEvent, useState } from "react";

import { requestJson } from "../../api/client";
import { supabase } from "../../lib/supabase";
import { useAuth } from "../auth/auth-context";
import { useWorkspace } from "../workspaces/workspace-context";

type Usage = {
  documents: number;
  document_bytes: number;
  ready_documents: number;
  conversations: number;
  runs: number;
  approvals: number;
  memories: number;
};

function formatBytes(size: number): string {
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function SettingsPage() {
  const { session, user } = useAuth();
  const { activeWorkspace } = useWorkspace();
  const queryClient = useQueryClient();
  const [name, setName] = useState(activeWorkspace?.name ?? "");
  const workspaceId = activeWorkspace?.id;
  const headers = {
    Authorization: `Bearer ${session?.access_token ?? ""}`,
    "X-Workspace-ID": workspaceId ?? "",
  };
  const usage = useQuery({
    queryKey: ["usage", workspaceId],
    enabled: Boolean(session && workspaceId),
    queryFn: () => requestJson<Usage>("/v1/workspace/usage", { headers }),
  });
  const rename = useMutation({
    mutationFn: async () => {
      if (!supabase || !workspaceId) throw new Error("Workspace unavailable");
      const { error } = await supabase
        .from("workspaces")
        .update({ name: name.trim() })
        .eq("id", workspaceId);
      if (error) throw error;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["workspaces", user?.id] });
    },
  });
  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (name.trim().length >= 2) rename.mutate();
  };
  const data = usage.data;
  const storagePercent = Math.min(
    100,
    ((data?.document_bytes ?? 0) / (35 * 1024 * 1024)) * 100,
  );

  return (
    <section aria-labelledby="settings-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Workspace administration</p>
          <h1 id="settings-title">Settings</h1>
        </div>
      </div>

      <div className="settings-layout">
        <section className="settings-section" aria-labelledby="workspace-settings-title">
          <h2 id="workspace-settings-title">Workspace</h2>
          <form className="settings-form" onSubmit={submit}>
            <label htmlFor="settings-workspace-name">Workspace name</label>
            <div>
              <input
                id="settings-workspace-name"
                minLength={2}
                maxLength={80}
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                }}
              />
              <button
                className="primary-button settings-save"
                type="submit"
                disabled={rename.isPending || name.trim() === activeWorkspace?.name}
              >
                {rename.isSuccess ? <Check size={17} /> : <Save size={17} />}
                {rename.isSuccess ? "Saved" : "Save"}
              </button>
            </div>
          </form>
          {rename.isError ? (
            <p className="form-message form-error" role="alert">
              The workspace name could not be updated.
            </p>
          ) : null}
          <dl className="identity-list">
            <div><dt>Session</dt><dd>Guest</dd></div>
            <div><dt>Role</dt><dd>Workspace owner</dd></div>
            <div><dt>User ID</dt><dd>{user?.id.slice(0, 8) ?? "-"}</dd></div>
          </dl>
        </section>

        <section className="settings-section usage-section" aria-labelledby="usage-title">
          <div className="section-heading">
            <h2 id="usage-title">Usage</h2>
            <p>Current durable records in this workspace.</p>
          </div>
          {usage.isLoading ? <p className="table-message">Loading usage...</p> : null}
          {usage.isError ? (
            <p className="form-message form-error">Usage could not be loaded.</p>
          ) : null}
          {data ? (
            <>
              <div className="usage-grid">
                <div><FileStack size={18} /><span>Documents</span><strong>{data.documents}</strong></div>
                <div><MessageSquareText size={18} /><span>Conversations</span><strong>{data.conversations}</strong></div>
                <div><Gauge size={18} /><span>Runs</span><strong>{data.runs}</strong></div>
                <div><ShieldCheck size={18} /><span>Reviews</span><strong>{data.approvals}</strong></div>
              </div>
              <div className="storage-meter">
                <div>
                  <span><Database size={16} /> Document storage</span>
                  <strong>{formatBytes(data.document_bytes)} / 35 MB</strong>
                </div>
                <progress value={storagePercent} max={100}>
                  {storagePercent.toFixed(1)}%
                </progress>
              </div>
            </>
          ) : null}
        </section>
      </div>
    </section>
  );
}
