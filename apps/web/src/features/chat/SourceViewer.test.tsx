import { fireEvent, screen, waitFor } from "@testing-library/react";
import { render } from "@testing-library/react";

import { SourceViewer } from "./SourceViewer";

const citation = {
  citation_id: "C1",
  document_id: "document-1",
  chunk_id: "chunk-1",
  label: "Operations",
  page: 2,
  section: "Reset",
  quote: "Rotate the emergency token.",
  source_url: "/v1/documents/document-1/source?page=2",
};

test("loads a protected source and supports close controls", async () => {
  const close = vi.fn();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    Response.json({
      url: "https://signed.example/document#page=2",
      expires_at: "2099-01-01T00:00:00Z",
    }),
  );

  render(
    <SourceViewer
      citation={citation}
      accessToken="token"
      workspaceId="workspace-1"
      onClose={close}
    />,
  );

  await waitFor(() => {
    expect(screen.getByTitle("Operations")).toHaveAttribute(
      "src",
      "https://signed.example/document#page=2",
    );
  });
  expect(globalThis.fetch).toHaveBeenCalledWith(
    expect.stringContaining("/v1/documents/document-1/source-url?page=2"),
    expect.any(Object),
  );
  fireEvent.click(screen.getByRole("button", { name: "Close source" }));
  fireEvent.mouseDown(screen.getByRole("presentation"));
  expect(close).toHaveBeenCalledTimes(2);
});

test("shows a protected-source error", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 404 }));
  render(
    <SourceViewer
      citation={{
        ...citation,
        page: null,
        source_url: "/v1/documents/document-error/source",
      }}
      accessToken="token"
      workspaceId="workspace-1"
      onClose={vi.fn()}
    />,
  );
  expect(await screen.findByText(/could not be opened/)).toBeInTheDocument();
});

test("opens a source without a page fragment", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    Response.json({
      url: "https://signed.example/plain-source",
      expires_at: "2099-01-01T00:00:00Z",
    }),
  );
  render(
    <SourceViewer
      citation={{
        ...citation,
        page: null,
        source_url: "/v1/documents/document-plain/source",
      }}
      accessToken="token"
      workspaceId="workspace-1"
      onClose={vi.fn()}
    />,
  );
  await waitFor(() => {
    expect(screen.getByTitle("Operations")).toHaveAttribute(
      "src",
      "https://signed.example/plain-source",
    );
  });
});

test("renders citation dialog and Evidence metadata", () => {
  render(
    <SourceViewer
      citation={{
        ...citation,
        quote:
          "### Diagram: Figure 4-12\n\n![Figure 4-12 architecture](https://example.com/fig.jpeg)\n\n**Figure Context**: Token bucket rate limiting details.",
      }}
      accessToken="token"
      workspaceId="workspace-1"
      onClose={vi.fn()}
    />,
  );

  expect(screen.getByRole("dialog", { name: "Operations" })).toBeInTheDocument();
  expect(screen.getByText(/Evidence C1/)).toBeInTheDocument();
});

test("loads and displays single page preview with highlight", async () => {
  Object.defineProperty(globalThis.URL, "createObjectURL", {
    value: () => "blob:https://signed.example/page-2.png",
    writable: true,
    configurable: true,
  });
  const blob = new Blob(["fake-image-bytes"], { type: "image/png" });
  vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (url.includes("/preview")) {
      return Promise.resolve(new Response(blob, { status: 200 }));
    }
    return Promise.resolve(
      Response.json({
        url: "https://signed.example/document#page=2",
        expires_at: "2099-01-01T00:00:00Z",
      }),
    );
  });

  render(
    <SourceViewer
      citation={{
        ...citation,
        quote: "Review the [system guide](https://example.com/guide) for details.",
      }}
      accessToken="token"
      workspaceId="workspace-1"
      onClose={vi.fn()}
    />,
  );

  const pageImg = await screen.findByAltText("Page 2 with highlighted citation");
  expect(pageImg).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Fullscreen/ })).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /Open.*in a new tab/i }).length).toBeGreaterThan(0);
  fireEvent.click(pageImg);
  expect(
    await screen.findByRole("dialog", { name: "Enlarged diagram" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Close image preview" }));
  fireEvent.click(screen.getByRole("button", { name: /Fullscreen/ }));
  expect(
    await screen.findByRole("dialog", { name: "Enlarged diagram" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("dialog", { name: "Enlarged diagram" }));
  expect(screen.queryByRole("dialog", { name: "Enlarged diagram" })).not.toBeInTheDocument();
});

test("handles escape key, backdrop click, dialog propagation, and cached source", () => {
  const close = vi.fn();
  const { container } = render(
    <SourceViewer
      citation={{
        ...citation,
        page: null,
        section: null,
        source_url: "https://signed.example/cached-source",
      }}
      accessToken="token"
      workspaceId="workspace-1"
      onClose={close}
    />,
  );

  fireEvent.keyDown(window, { key: "Escape" });
  expect(close).toHaveBeenCalled();

  const overlay = container.querySelector(".source-overlay");
  expect(overlay).not.toBeNull();
  if (overlay) fireEvent.mouseDown(overlay);
  expect(close).toHaveBeenCalledTimes(2);

  const dialog = screen.getByRole("dialog", { name: "Operations" });
  fireEvent.mouseDown(dialog);
  expect(close).toHaveBeenCalledTimes(2);
});

