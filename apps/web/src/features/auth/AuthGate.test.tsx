import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AuthContextValue } from "./auth-context";
import { AuthGate } from "./AuthGate";

const state = vi.hoisted(() => ({
  auth: null as AuthContextValue | null,
}));

vi.mock("./auth-context", () => ({
  useAuth: () => state.auth,
}));

function authValue(
  overrides: Partial<AuthContextValue> = {},
): AuthContextValue {
  return {
    session: null,
    user: null,
    status: "anonymous",
    signInWithEmail: vi.fn(),
    signOut: vi.fn(),
    ...overrides,
  };
}

test("shows session restoration and configuration states", () => {
  state.auth = authValue({ status: "loading" });
  const view = render(
    <AuthGate>
      <p>Private content</p>
    </AuthGate>,
  );
  expect(screen.getByText("Restoring your secure session")).toBeInTheDocument();

  state.auth = authValue({ status: "unconfigured" });
  view.rerender(
    <AuthGate>
      <p>Private content</p>
    </AuthGate>,
  );
  expect(
    screen.getByRole("heading", { name: "Authentication needs configuration" }),
  ).toBeInTheDocument();
});

test("renders protected content for an authenticated user", () => {
  state.auth = authValue({ status: "authenticated" });

  render(
    <AuthGate>
      <p>Private content</p>
    </AuthGate>,
  );

  expect(screen.getByText("Private content")).toBeInTheDocument();
});

test("sends a passwordless sign-in link", async () => {
  const user = userEvent.setup();
  const signInWithEmail = vi.fn().mockResolvedValue(undefined);
  state.auth = authValue({ signInWithEmail });
  render(
    <AuthGate>
      <p>Private content</p>
    </AuthGate>,
  );

  await user.type(screen.getByLabelText("Email address"), "pat@example.test");
  await user.click(screen.getByRole("button", { name: "Send sign-in link" }));

  expect(signInWithEmail).toHaveBeenCalledWith("pat@example.test");
  expect(
    screen.getByText("Check your email for a secure sign-in link."),
  ).toBeInTheDocument();
});

test("reports a passwordless sign-in failure", async () => {
  const user = userEvent.setup();
  state.auth = authValue({
    signInWithEmail: vi.fn().mockRejectedValue(new Error("provider failed")),
  });
  render(
    <AuthGate>
      <p>Private content</p>
    </AuthGate>,
  );

  await user.type(screen.getByLabelText("Email address"), "pat@example.test");
  await user.click(screen.getByRole("button", { name: "Send sign-in link" }));

  expect(screen.getByRole("alert")).toHaveTextContent(
    "The sign-in link could not be sent.",
  );
});
