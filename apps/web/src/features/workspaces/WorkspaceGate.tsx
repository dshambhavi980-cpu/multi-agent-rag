import { Building2, LoaderCircle, Plus } from "lucide-react";
import { type PropsWithChildren, type SyntheticEvent, useState } from "react";

import { useWorkspace } from "./workspace-context";

export function WorkspaceGate({ children }: PropsWithChildren) {
  const { activeWorkspace, createWorkspace, creating, error, loading } = useWorkspace();
  const [name, setName] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (loading) {
    return (
      <main className="auth-page">
        <LoaderCircle className="spin" aria-hidden="true" />
        <p>Loading your workspaces</p>
      </main>
    );
  }

  if (activeWorkspace) {
    return children;
  }

  const submit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);
    try {
      await createWorkspace(name);
    } catch {
      setSubmitError("The workspace could not be created. Please try again.");
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="workspace-title">
        <Building2 aria-hidden="true" size={28} />
        <h1 id="workspace-title">Create your first workspace</h1>
        <p>Documents, conversations, and agent runs stay isolated inside it.</p>
        <form onSubmit={(event) => void submit(event)}>
          <label htmlFor="workspace-name">Workspace name</label>
          <input
            id="workspace-name"
            minLength={2}
            maxLength={80}
            required
            value={name}
            onChange={(event) => {
              setName(event.target.value);
            }}
            placeholder="Internal knowledge"
          />
          <button className="primary-button auth-submit" type="submit" disabled={creating}>
            {creating ? (
              <LoaderCircle className="spin" aria-hidden="true" size={17} />
            ) : (
              <Plus aria-hidden="true" size={17} />
            )}
            Create workspace
          </button>
        </form>
        {error || submitError ? (
          <p className="form-message form-error" role="alert">
            {error ?? submitError}
          </p>
        ) : null}
      </section>
    </main>
  );
}
