import { render, screen } from "@testing-library/react";

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
  expect(screen.getByText("Preparing your guest workspace")).toBeInTheDocument();

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

test("shows a guest access error without a sign-in form", () => {
  state.auth = authValue({ status: "anonymous" });
  render(
    <AuthGate>
      <p>Private content</p>
    </AuthGate>,
  );

  expect(
    screen.getByRole("heading", { name: "Guest access is unavailable" }),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Email address")).not.toBeInTheDocument();
});
