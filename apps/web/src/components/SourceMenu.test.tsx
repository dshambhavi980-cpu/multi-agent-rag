import { fireEvent, render, screen } from "@testing-library/react";

import { SourceMenu } from "./SourceMenu";

test("selects sources and closes when clicking outside", () => {
  const onChange = vi.fn();
  render(
    <div>
      <SourceMenu
        options={[{ id: "document-1", label: "Architecture guide" }]}
        selected={[]}
        onChange={onChange}
      />
      <button type="button">Outside</button>
    </div>,
  );

  fireEvent.click(screen.getByRole("button", { name: /all sources/i }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Architecture guide" }));
  expect(onChange).toHaveBeenCalledWith(["document-1"]);

  fireEvent.mouseDown(screen.getByRole("button", { name: "Outside" }));
  expect(screen.queryByRole("dialog", { name: "Source documents" })).not.toBeInTheDocument();
});

test("shows selected scope, clears it, and closes with Escape", () => {
  const onChange = vi.fn();
  render(
    <SourceMenu
      options={[{ id: "document-1", label: "Architecture guide" }]}
      selected={["document-1"]}
      onChange={onChange}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: /1 sources/i }));
  expect(screen.getByText("Only selected documents")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Search all documents" }));
  expect(onChange).toHaveBeenCalledWith([]);

  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog", { name: "Source documents" })).not.toBeInTheDocument();
});

test("shows an empty state and supports the close control", () => {
  render(<SourceMenu options={[]} selected={[]} onChange={vi.fn()} />);

  fireEvent.click(screen.getByRole("button", { name: /all sources/i }));
  expect(screen.getByText("No indexed sources yet.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Close source selector" }));
  expect(screen.queryByRole("dialog", { name: "Source documents" })).not.toBeInTheDocument();
});
