import type { Session } from "@supabase/supabase-js";
import {
  type PropsWithChildren,
  useEffect,
  useMemo,
  useState,
} from "react";

import { supabase } from "../../lib/supabase";
import {
  AuthContext,
  type AuthContextValue,
  type AuthStatus,
} from "./auth-context";

export function AuthProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<AuthStatus>(
    supabase ? "loading" : "unconfigured",
  );

  useEffect(() => {
    const client = supabase;
    if (!client) {
      return;
    }

    const lifecycle = new AbortController();
    const isCancelled = () => lifecycle.signal.aborted;
    const restoreOrCreateGuestSession = async () => {
      const { data, error } = await client.auth.getSession();
      if (isCancelled()) {
        return;
      }
      if (error) {
        setSession(null);
        setStatus("anonymous");
        return;
      }
      if (data.session) {
        setSession(data.session);
        setStatus("authenticated");
        return;
      }

      const { data: guestData, error: guestError } =
        await client.auth.signInAnonymously();
      if (isCancelled()) {
        return;
      }
      if (guestError || !guestData.session) {
        setSession(null);
        setStatus("anonymous");
        return;
      }
      setSession(guestData.session);
      setStatus("authenticated");
    };
    void restoreOrCreateGuestSession();

    const {
      data: { subscription },
    } = client.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setStatus(nextSession ? "authenticated" : "anonymous");
    });

    return () => {
      lifecycle.abort();
      subscription.unsubscribe();
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      user: session?.user ?? null,
      status,
    }),
    [session, status],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
