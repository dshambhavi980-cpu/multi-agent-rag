import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SegmentedControl } from "./SegmentedControl";

describe("SegmentedControl", () => {
  it("renders options and highlights the active option", () => {
    const handleChange = vi.fn();
    render(
      <SegmentedControl
        label="Test view"
        value="all"
        options={["all", "private", "workspace"]}
        onChange={handleChange}
      />,
    );

    const allBtn = screen.getByRole("button", { name: "All" });
    const privateBtn = screen.getByRole("button", { name: "Private" });

    expect(allBtn).toHaveAttribute("aria-pressed", "true");
    expect(privateBtn).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(allBtn);
    expect(handleChange).not.toHaveBeenCalled();

    fireEvent.click(privateBtn);
    expect(handleChange).toHaveBeenCalledWith("private");
  });

  it("handles object options with custom labels", () => {
    const handleChange = vi.fn();
    render(
      <SegmentedControl
        label="Custom options"
        value="first"
        options={[
          { value: "first", label: "Option One" },
          { value: "second", label: "Option Two" },
        ]}
        onChange={handleChange}
        size="sm"
      />,
    );

    expect(screen.getByRole("button", { name: "Option One" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Option Two" }));
    expect(handleChange).toHaveBeenCalledWith("second");
  });
});
