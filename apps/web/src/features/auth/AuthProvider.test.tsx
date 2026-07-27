import type { Session } from "@supabase/supabase-js";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { useAuth } from "./auth-context";
import { AuthProvider } from "./AuthProvider";

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  signInWithOtp: vi.fn(),
  signOut: vi.fn(),
  unsubscribe: vi.fn(),
  authChange: null as ((event: string, session: Session | null) => void) | null,
}));

vi.mock("../../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: mocks.getSession,
      onAuthStateChange: mocks.onAuthStateChange,
      signInWithOtp: mocks.signInWithOtp,
      signOut: mocks.signOut,
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
      <button type="button" onClick={() => void auth.signInWithEmail("pat@example.test")}>
        Sign in
      </button>
      <button type="button" onClick={() => void auth.signOut()}>
        Sign out
      </button>
    </>
  );
}

beforeEach(() => {
  mocks.getSession.mockReset();
  mocks.onAuthStateChange.mockReset();
  mocks.signInWithOtp.mockReset();
  mocks.signOut.mockReset();
  mocks.unsubscribe.mockReset();
  mocks.authChange = null;
  mocks.onAuthStateChange.mockImplementation(
    (callback: (event: string, nextSession: Session | null) => void) => {
      mocks.authChange = callback;
      return { data: { subscription: { unsubscribe: mocks.unsubscribe } } };
    },
  );
  mocks.signInWithOtp.mockResolvedValue({ error: null });
  mocks.signOut.mockResolvedValue({ error: null });
});

test("restores a session and manages passwordless auth", async () => {
  const user = userEvent.setup();
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

  await user.click(screen.getByRole("button", { name: "Sign in" }));
  expect(mocks.signInWithOtp).toHaveBeenCalledWith({
    email: "pat@example.test",
    options: {
      emailRedirectTo: "http://localhost:3000",
      shouldCreateUser: true,
    },
  });

  await user.click(screen.getByRole("button", { name: "Sign out" }));
  expect(mocks.signOut).toHaveBeenCalled();

  act(() => {
    mocks.authChange?.("SIGNED_OUT", null);
  });
  expect(screen.getByText("anonymous")).toBeInTheDocument();

  view.unmount();
  expect(mocks.unsubscribe).toHaveBeenCalled();
});

test("falls back to anonymous when session restoration fails", async () => {
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

test("propagates provider errors from sign-in and sign-out", async () => {
  mocks.getSession.mockResolvedValue({ data: { session }, error: null });
  mocks.signInWithOtp.mockResolvedValue({ error: new Error("sign in failed") });
  mocks.signOut.mockResolvedValue({ error: new Error("sign out failed") });

  function ErrorConsumer() {
    const auth = useAuth();
    return (
      <>
        <button
          type="button"
          onClick={() => {
            void auth.signInWithEmail("pat@example.test").catch(() => undefined);
          }}
        >
          Failing sign in
        </button>
        <button
          type="button"
          onClick={() => {
            void auth.signOut().catch(() => undefined);
          }}
        >
          Failing sign out
        </button>
      </>
    );
  }

  const user = userEvent.setup();
  render(
    <AuthProvider>
      <ErrorConsumer />
    </AuthProvider>,
  );
  await user.click(screen.getByRole("button", { name: "Failing sign in" }));
  await user.click(screen.getByRole("button", { name: "Failing sign out" }));

  expect(mocks.signInWithOtp).toHaveBeenCalled();
  expect(mocks.signOut).toHaveBeenCalled();
});
