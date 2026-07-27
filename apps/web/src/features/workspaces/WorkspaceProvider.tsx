import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type PropsWithChildren,
  useState,
} from "react";

import { supabase } from "../../lib/supabase";
import { useAuth } from "../auth/auth-context";
import { WorkspaceContext, type WorkspaceContextValue } from "./workspace-context";

export function WorkspaceProvider({ children }: PropsWithChildren) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(
    () => window.localStorage.getItem("docpilot.activeWorkspaceId"),
  );

  const workspaceQuery = useQuery({
    queryKey: ["workspaces", user?.id],
    enabled: Boolean(user && supabase),
    queryFn: async () => {
      if (!supabase) {
        return [];
      }
      const { data, error } = await supabase
        .from("workspaces")
        .select("*")
        .order("created_at", { ascending: true });
      if (error) {
        throw error;
      }
      return data;
    },
  });

  const workspaces = workspaceQuery.data ?? [];
  const activeWorkspace =
    workspaces.find((workspace) => workspace.id === activeWorkspaceId) ??
    workspaces[0] ??
    null;

  const createMutation = useMutation({
    mutationFn: async (name: string) => {
      if (!supabase || !user) {
        throw new Error("A signed-in user is required.");
      }
      const { data, error } = await supabase
        .from("workspaces")
        .insert({ name: name.trim(), created_by: user.id })
        .select("*")
        .single();
      if (error) {
        throw error;
      }
      return data;
    },
    onSuccess: async (workspace) => {
      setActiveWorkspaceId(workspace.id);
      window.localStorage.setItem("docpilot.activeWorkspaceId", workspace.id);
      await queryClient.invalidateQueries({ queryKey: ["workspaces", user?.id] });
    },
  });

  const value: WorkspaceContextValue = {
    workspaces,
    activeWorkspace,
    loading: workspaceQuery.isLoading,
    error: workspaceQuery.error ? "Workspaces could not be loaded." : null,
    creating: createMutation.isPending,
    createWorkspace: async (name: string) => {
      await createMutation.mutateAsync(name);
    },
    selectWorkspace: (workspaceId: string) => {
      setActiveWorkspaceId(workspaceId);
      window.localStorage.setItem("docpilot.activeWorkspaceId", workspaceId);
    },
  };

  return (
    <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
  );
}
