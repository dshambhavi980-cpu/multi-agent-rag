import type { Session, User } from "@supabase/supabase-js";
import { createContext, useContext } from "react";

export type AuthStatus =
  | "loading"
  | "authenticated"
  | "anonymous"
  | "unconfigured";

export type AuthContextValue = {
  session: Session | null;
  user: User | null;
  status: AuthStatus;
  signInWithEmail: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return context;
}
