import { render, screen } from "@testing-library/react";

import { AuthContext, type AuthContextValue, useAuth } from "./auth-context";

function Consumer() {
  return <p>{useAuth().status}</p>;
}

test("provides authentication state", () => {
  const value: AuthContextValue = {
    session: null,
    user: null,
    status: "anonymous",
  };

  render(
    <AuthContext.Provider value={value}>
      <Consumer />
    </AuthContext.Provider>,
  );

  expect(screen.getByText("anonymous")).toBeInTheDocument();
});

test("requires the authentication provider", () => {
  expect(() => render(<Consumer />)).toThrow(
    "useAuth must be used within AuthProvider.",
  );
});
