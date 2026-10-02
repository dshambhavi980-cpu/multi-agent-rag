import { HugeiconsIcon } from "@hugeicons/react";
import {
  Building01Icon,
  Loading03Icon,
  PlusSignIcon,
} from "@hugeicons/core-free-icons";
import { type PropsWithChildren, type SyntheticEvent, useState } from "react";

import { useWorkspace } from "./workspace-context";

export function WorkspaceGate({ children }: PropsWithChildren) {
  const { activeWorkspace, createWorkspace, creating, error, loading } = useWorkspace();
  const [name, setName] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (loading) {
    return (
      <main className="auth-page">
        <HugeiconsIcon icon={Loading03Icon} className="spin" aria-hidden="true" size={24} strokeWidth={1.8} />
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
        <HugeiconsIcon icon={Building01Icon} aria-hidden="true" size={28} strokeWidth={1.8} />
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
              <HugeiconsIcon icon={Loading03Icon} className="spin" aria-hidden="true" size={17} strokeWidth={1.8} />
            ) : (
              <HugeiconsIcon icon={PlusSignIcon} aria-hidden="true" size={17} strokeWidth={2} />
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
