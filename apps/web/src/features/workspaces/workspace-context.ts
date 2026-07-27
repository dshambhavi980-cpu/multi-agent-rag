import { createContext, useContext } from "react";

import type { Workspace } from "../../types/database.types";

export type WorkspaceContextValue = {
  workspaces: Workspace[];
  activeWorkspace: Workspace | null;
  loading: boolean;
  error: string | null;
  creating: boolean;
  createWorkspace: (name: string) => Promise<void>;
  selectWorkspace: (workspaceId: string) => void;
};

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function useWorkspace(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used within WorkspaceProvider.");
  }
  return context;
}
