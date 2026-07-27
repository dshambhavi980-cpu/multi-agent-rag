import { KeyRound, LoaderCircle, Mail, Send } from "lucide-react";
import { type PropsWithChildren, type SyntheticEvent, useState } from "react";

import { useAuth } from "./auth-context";

export function AuthGate({ children }: PropsWithChildren) {
  const { status, signInWithEmail } = useAuth();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (status === "authenticated") {
    return children;
  }

  if (status === "loading") {
    return (
      <main className="auth-page">
        <LoaderCircle className="spin" aria-hidden="true" />
        <p>Restoring your secure session</p>
      </main>
    );
  }

  if (status === "unconfigured") {
    return (
      <main className="auth-page">
        <section className="auth-panel" aria-labelledby="auth-config-title">
          <KeyRound aria-hidden="true" size={28} />
          <h1 id="auth-config-title">Authentication needs configuration</h1>
          <p>Add the Supabase URL and publishable key to the web environment.</p>
        </section>
      </main>
    );
  }

  const submit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      await signInWithEmail(email.trim());
      setMessage("Check your email for a secure sign-in link.");
    } catch {
      setError("The sign-in link could not be sent. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="sign-in-title">
        <div className="auth-brand">
          <span className="brand-mark" aria-hidden="true">
            D
          </span>
          <span>DocPilot</span>
        </div>
        <h1 id="sign-in-title">Sign in to your workspace</h1>
        <p>Use your work email. We will send a passwordless sign-in link.</p>
        <form onSubmit={(event) => void submit(event)}>
          <label htmlFor="email">Email address</label>
          <div className="input-with-icon">
            <Mail aria-hidden="true" size={17} />
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
              }}
              placeholder="you@company.com"
            />
          </div>
          <button className="primary-button auth-submit" type="submit" disabled={submitting}>
            {submitting ? (
              <LoaderCircle className="spin" aria-hidden="true" size={17} />
            ) : (
              <Send aria-hidden="true" size={17} />
            )}
            Send sign-in link
          </button>
        </form>
        {message ? <p className="form-message form-success">{message}</p> : null}
        {error ? (
          <p className="form-message form-error" role="alert">
            {error}
          </p>
        ) : null}
      </section>
    </main>
  );
}
