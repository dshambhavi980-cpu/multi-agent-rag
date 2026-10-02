import { HugeiconsIcon } from "@hugeicons/react";
import {
  Alert01Icon,
  Loading03Icon,
  ShieldKeyIcon,
} from "@hugeicons/core-free-icons";
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
        <HugeiconsIcon icon={Loading03Icon} className="spin" aria-hidden="true" size={24} strokeWidth={1.8} />
        <p>Preparing your guest workspace</p>
      </main>
    );
  }

  if (status === "unconfigured") {
    return (
      <main className="auth-page">
        <section className="auth-panel" aria-labelledby="auth-config-title">
          <HugeiconsIcon icon={ShieldKeyIcon} aria-hidden="true" size={28} strokeWidth={1.8} />
          <h1 id="auth-config-title">Authentication needs configuration</h1>
          <p>Add the Supabase URL and publishable key to the web environment.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="guest-error-title">
        <HugeiconsIcon icon={Alert01Icon} aria-hidden="true" size={28} strokeWidth={1.8} />
        <h1 id="guest-error-title">Guest access is unavailable</h1>
        <p>Anonymous access must be enabled in the Supabase Auth settings.</p>
      </section>
    </main>
  );
}
