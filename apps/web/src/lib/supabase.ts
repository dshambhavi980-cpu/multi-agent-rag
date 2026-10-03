import { createClient } from "@supabase/supabase-js";

import type { Database } from "../types/database.types";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabasePublishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const supabase =
  supabaseUrl && supabasePublishableKey
    ? createClient<Database>(supabaseUrl, supabasePublishableKey, {
        auth: {
          autoRefreshToken: true,
          detectSessionInUrl: true,
          persistSession: true,
        },
      })
    : null;

export async function getFreshAccessToken(
  fallbackToken?: string | null,
): Promise<string | null> {
  if (supabase) {
    try {
      const { data, error } = await supabase.auth.getSession();
      if (!error && data.session?.access_token) {
        return data.session.access_token;
      }
      const { data: refreshData, error: refreshError } =
        await supabase.auth.refreshSession();
      if (!refreshError && refreshData.session?.access_token) {
        return refreshData.session.access_token;
      }
      const { data: anonData, error: anonError } =
        await supabase.auth.signInAnonymously();
      if (!anonError && anonData.session?.access_token) {
        return anonData.session.access_token;
      }
    } catch {
      // Fall back below
    }
  }
  return fallbackToken ?? null;
}

