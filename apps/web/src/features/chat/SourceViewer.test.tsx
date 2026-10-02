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

test("renders formatted markdown citation content and opens image lightbox", async () => {
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

  expect(screen.getByRole("heading", { level: 3, name: "Diagram: Figure 4-12" })).toBeInTheDocument();
  const img = screen.getByAltText("Figure 4-12 architecture");
  expect(img).toBeInTheDocument();
  expect(screen.getByText(/Token bucket rate limiting details/)).toBeInTheDocument();

  fireEvent.click(img);
  expect(screen.getByRole("dialog", { name: "Enlarged diagram" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Close image preview" }));
  expect(screen.queryByRole("dialog", { name: "Enlarged diagram" })).not.toBeInTheDocument();
});

