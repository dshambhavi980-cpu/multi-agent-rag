import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Thinking } from "./Thinking";

describe("Thinking", () => {
  it("renders Thinking text and orb component", () => {
    render(<Thinking />);
    expect(screen.getByText("Thinking")).toBeInTheDocument();
  });
});
