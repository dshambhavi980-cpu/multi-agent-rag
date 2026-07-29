import {
  BookOpenText,
  Bot,
  ChartNoAxesCombined,
  Database,
  FileStack,
  Gauge,
  Menu,
  MessageSquareText,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";

import { AuthGate } from "../features/auth/AuthGate";
import { SystemOverview } from "../features/system/SystemOverview";
import { WorkspaceGate } from "../features/workspaces/WorkspaceGate";
import { useWorkspace } from "../features/workspaces/workspace-context";

const ApprovalsPage = lazy(() =>
  import("../features/approvals/ApprovalsPage").then((module) => ({
    default: module.ApprovalsPage,
  })),
);
const ChatPage = lazy(() =>
  import("../features/chat/ChatPage").then((module) => ({ default: module.ChatPage })),
);
const DocumentsPage = lazy(() =>
  import("../features/documents/DocumentsPage").then((module) => ({
    default: module.DocumentsPage,
  })),
);
const EvaluationsPage = lazy(() =>
  import("../features/evaluations/EvaluationsPage").then((module) => ({
    default: module.EvaluationsPage,
  })),
);
const MemoryPage = lazy(() =>
  import("../features/memory/MemoryPage").then((module) => ({
    default: module.MemoryPage,
  })),
);
const RunsPage = lazy(() =>
  import("../features/runs/RunsPage").then((module) => ({ default: module.RunsPage })),
);
const SettingsPage = lazy(() =>
  import("../features/settings/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);

const navigation = [
  { label: "Overview", icon: Gauge, path: "/" },
  { label: "Chat", icon: MessageSquareText, path: "/chat" },
  { label: "Documents", icon: FileStack, path: "/documents" },
  { label: "Agent runs", icon: Bot, path: "/runs" },
  { label: "Review queue", icon: ShieldCheck, path: "/approvals" },
  { label: "Evaluations", icon: ChartNoAxesCombined, path: "/evaluations" },
  { label: "Memory", icon: Database, path: "/memory" },
];

const routeTitles: Record<string, string> = {
  "/chat": "Chat",
  "/documents": "Documents",
  "/runs": "Agent runs",
  "/approvals": "Review queue",
  "/evaluations": "Evaluations",
  "/memory": "Memory",
  "/settings": "Settings",
};

function Placeholder({ title }: { title: string }) {
  return (
    <section className="empty-state" aria-labelledby="placeholder-title">
      <BookOpenText aria-hidden="true" size={28} />
      <h1 id="placeholder-title">{title}</h1>
      <p>This workspace will be connected in its implementation phase.</p>
    </section>
  );
}

function AuthenticatedApp() {
  const { activeWorkspace, selectWorkspace, workspaces } = useWorkspace();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [pathname, setPathname] = useState(window.location.pathname);

  useEffect(() => {
    const updatePathname = () => {
      setPathname(window.location.pathname);
    };
    window.addEventListener("popstate", updatePathname);
    return () => {
      window.removeEventListener("popstate", updatePathname);
    };
  }, []);

  const navigate = (path: string) => {
    if (path !== pathname) {
      window.history.pushState(null, "", path);
      setPathname(path);
    }
    setMobileNavigationOpen(false);
  };

  const routeContent =
    pathname === "/" ? <SystemOverview /> :
    pathname === "/chat" ? <ChatPage /> :
    pathname === "/documents" ? <DocumentsPage /> :
    pathname === "/runs" ? <RunsPage /> :
    pathname === "/approvals" ? <ApprovalsPage /> :
    pathname === "/evaluations" ? <EvaluationsPage /> :
    pathname === "/memory" ? <MemoryPage /> :
    pathname === "/settings" ? <SettingsPage /> :
    <Placeholder title={routeTitles[pathname] ?? "Not found"} />;

  return (
    <div className="app-shell">
      <aside
        className={mobileNavigationOpen ? "sidebar sidebar-open" : "sidebar"}
      >
        <div className="brand-row">
          <span className="brand-mark" aria-hidden="true">
            D
          </span>
          <span className="brand-name">DocPilot</span>
          <button
            className="icon-button mobile-only"
            type="button"
            aria-label="Close navigation"
            onClick={() => {
              setMobileNavigationOpen(false);
            }}
          >
            <X size={19} />
          </button>
        </div>

        <nav className="nav-list" aria-label="Primary navigation">
          {navigation.map(({ label, icon: Icon, path }) => (
            <a
              key={path}
              href={path}
              aria-current={pathname === path ? "page" : undefined}
              onClick={(event) => {
                event.preventDefault();
                navigate(path);
              }}
              className={pathname === path ? "nav-link nav-link-active" : "nav-link"}
            >
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </a>
          ))}
        </nav>

        <a
          className={
            pathname === "/settings"
              ? "nav-link nav-link-active settings-link"
              : "nav-link settings-link"
          }
          href="/settings"
          aria-current={pathname === "/settings" ? "page" : undefined}
          onClick={(event) => {
            event.preventDefault();
            navigate("/settings");
          }}
        >
          <Settings size={18} aria-hidden="true" />
          <span>Settings</span>
        </a>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <button
            className="icon-button mobile-only"
            type="button"
            aria-label="Open navigation"
            onClick={() => {
              setMobileNavigationOpen(true);
            }}
          >
            <Menu size={20} />
          </button>
          <label className="workspace-switcher">
            <span className="sr-only">Active workspace</span>
            <select
              value={activeWorkspace?.id ?? ""}
              onChange={(event) => {
                selectWorkspace(event.target.value);
              }}
            >
              {workspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          </label>
          <div
            className="user-avatar"
            aria-label="Guest session"
            title="Guest session"
          >
            G
          </div>
        </header>

        <main className="main-content">
          <Suspense fallback={<p className="table-message">Loading workspace view...</p>}>
            {routeContent}
          </Suspense>
        </main>
      </div>

      {mobileNavigationOpen ? (
        <button
          className="sidebar-backdrop mobile-only"
          type="button"
          aria-label="Close navigation overlay"
          onClick={() => {
            setMobileNavigationOpen(false);
          }}
        />
      ) : null}
    </div>
  );
}

export function App() {
  return (
    <AuthGate>
      <WorkspaceGate>
        <AuthenticatedApp />
      </WorkspaceGate>
    </AuthGate>
  );
}
