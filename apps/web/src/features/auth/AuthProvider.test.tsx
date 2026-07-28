import type { Session } from "@supabase/supabase-js";
import { act, render, screen, waitFor } from "@testing-library/react";

import { useAuth } from "./auth-context";
import { AuthProvider } from "./AuthProvider";

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  signInAnonymously: vi.fn(),
  unsubscribe: vi.fn(),
  authChange: null as ((event: string, session: Session | null) => void) | null,
}));

vi.mock("../../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: mocks.getSession,
      onAuthStateChange: mocks.onAuthStateChange,
      signInAnonymously: mocks.signInAnonymously,
    },
  },
}));

const session = {
  access_token: "access",
  refresh_token: "refresh",
  expires_in: 3600,
  token_type: "bearer",
  user: {
    id: "user-1",
    email: "pat@example.test",
  },
} as Session;

function Consumer() {
  const auth = useAuth();
  return (
    <>
      <p>{auth.status}</p>
      <p>{auth.user?.email ?? "no user"}</p>
    </>
  );
}

beforeEach(() => {
  mocks.getSession.mockReset();
  mocks.onAuthStateChange.mockReset();
  mocks.signInAnonymously.mockReset();
  mocks.unsubscribe.mockReset();
  mocks.authChange = null;
  mocks.onAuthStateChange.mockImplementation(
    (callback: (event: string, nextSession: Session | null) => void) => {
      mocks.authChange = callback;
      return { data: { subscription: { unsubscribe: mocks.unsubscribe } } };
    },
  );
  mocks.signInAnonymously.mockResolvedValue({
    data: { session },
    error: null,
  });
});

test("restores an existing session", async () => {
  mocks.getSession.mockResolvedValue({ data: { session }, error: null });
  const view = render(
    <AuthProvider>
      <Consumer />
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText("authenticated")).toBeInTheDocument();
  });
  expect(screen.getByText("pat@example.test")).toBeInTheDocument();
  expect(mocks.signInAnonymously).not.toHaveBeenCalled();

  act(() => {
    mocks.authChange?.("SIGNED_OUT", null);
  });
  expect(screen.getByText("anonymous")).toBeInTheDocument();

  view.unmount();
  expect(mocks.unsubscribe).toHaveBeenCalled();
});

test("creates a guest session when none exists", async () => {
  mocks.getSession.mockResolvedValue({ data: { session: null }, error: null });

  render(
    <AuthProvider>
      <Consumer />
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText("authenticated")).toBeInTheDocument();
  });
  expect(mocks.signInAnonymously).toHaveBeenCalledOnce();
});

test("reports guest access as unavailable when restoration fails", async () => {
  mocks.getSession.mockResolvedValue({
    data: { session: null },
    error: new Error("storage failed"),
  });

  render(
    <AuthProvider>
      <Consumer />
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText("anonymous")).toBeInTheDocument();
  });
});

test("reports guest access as unavailable when anonymous sign-in fails", async () => {
  mocks.getSession.mockResolvedValue({ data: { session: null }, error: null });
  mocks.signInAnonymously.mockResolvedValue({
    data: { session: null },
    error: new Error("guest access disabled"),
  });

  render(
    <AuthProvider>
      <Consumer />
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText("anonymous")).toBeInTheDocument();
  });
});
