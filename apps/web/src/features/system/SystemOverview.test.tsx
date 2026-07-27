import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/render";
import { SystemOverview } from "./SystemOverview";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("renders warm operational status", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((request) => {
    const url =
      request instanceof Request
        ? request.url
        : request instanceof URL
          ? request.toString()
          : request;
    if (url.endsWith("/health")) {
      return Promise.resolve(
        response({
          status: "ok",
          time: "2026-07-28T00:00:00Z",
          cold_start: false,
        }),
      );
    }
    if (url.endsWith("/ready")) {
      return Promise.resolve(
        response({
          status: "ready",
          dependencies: { application: "ready" },
        }),
      );
    }
    return Promise.resolve(
      response({
        version: "0.1.0",
        commit: "test",
        environment: "test",
      }),
    );
  });

  renderWithProviders(<SystemOverview />);

  expect(await screen.findByText("Operational")).toBeInTheDocument();
  expect(screen.getByText("The API is warm and accepting traffic.")).toBeInTheDocument();
  expect(screen.getByText("0.1.0")).toBeInTheDocument();
  expect(screen.getByText("application")).toBeInTheDocument();
});

test("renders an actionable unreachable state", async () => {
  const user = userEvent.setup();
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network unavailable"));

  renderWithProviders(<SystemOverview />);

  expect(await screen.findByRole("alert")).toHaveTextContent("API unreachable");
  const retryButton = screen.getByRole("button", { name: "Retry" });
  expect(retryButton).toBeEnabled();
  await user.click(retryButton);
  expect(globalThis.fetch).toHaveBeenCalled();
});

test("distinguishes a recent degraded startup", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((request) => {
    const url =
      request instanceof Request
        ? request.url
        : request instanceof URL
          ? request.toString()
          : request;
    if (url.endsWith("/health")) {
      return Promise.resolve(
        response({
          status: "ok",
          time: "2026-07-28T00:00:00Z",
          cold_start: true,
        }),
      );
    }
    if (url.endsWith("/ready")) {
      return Promise.resolve(
        response({
          status: "degraded",
          dependencies: { application: "degraded" },
        }),
      );
    }
    return Promise.resolve(
      response({
        version: "0.1.0",
        commit: "test",
        environment: "preview",
      }),
    );
  });

  renderWithProviders(<SystemOverview />);

  expect(await screen.findByText("Attention required")).toBeInTheDocument();
  expect(screen.getByText("The API has recently started.")).toBeInTheDocument();
  expect(screen.getByText("preview")).toBeInTheDocument();
});
