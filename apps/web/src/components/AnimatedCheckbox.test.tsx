import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AnimatedCheckbox } from "./AnimatedCheckbox";

describe("AnimatedCheckbox", () => {
  it("renders checked state and triggers onChange when clicked", () => {
    const handleChange = vi.fn();
    render(
      <label>
        <AnimatedCheckbox
          checked={false}
          aria-label="Agree to terms"
          onChange={handleChange}
        />
        <span>Agree to terms</span>
      </label>,
    );

    const checkbox = screen.getByRole("checkbox", { name: "Agree to terms" });
    expect(checkbox).not.toBeChecked();

    fireEvent.click(checkbox);
    expect(handleChange).toHaveBeenCalledWith(true);
  });

  it("renders checked icon when checked is true", () => {
    render(
      <AnimatedCheckbox
        checked={true}
        aria-label="Verified"
      />,
    );

    const checkbox = screen.getByRole("checkbox", { name: "Verified" });
    expect(checkbox).toBeChecked();
  });
});
