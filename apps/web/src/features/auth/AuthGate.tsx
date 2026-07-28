import { KeyRound, LoaderCircle, TriangleAlert } from "lucide-react";
import type { PropsWithChildren } from "react";

import { useAuth } from "./auth-context";

export function AuthGate({ children }: PropsWithChildren) {
  const { status } = useAuth();

  if (status === "authenticated") {
    return children;
  }

  if (status === "loading") {
    return (
      <main className="auth-page">
        <LoaderCircle className="spin" aria-hidden="true" />
        <p>Preparing your guest workspace</p>
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

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="guest-error-title">
        <TriangleAlert aria-hidden="true" size={28} />
        <h1 id="guest-error-title">Guest access is unavailable</h1>
        <p>Anonymous access must be enabled in the Supabase Auth settings.</p>
      </section>
    </main>
  );
}
