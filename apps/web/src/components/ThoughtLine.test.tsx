import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ThoughtLine } from "./ThoughtLine";

describe("ThoughtLine", () => {
  it("renders working state with label and steps", () => {
    const handleSettle = vi.fn();
    render(
      <ThoughtLine
        working={true}
        label="Analyzing query…"
        steps={["Decomposing question", "Searching indices"]}
        onSettle={handleSettle}
      />,
    );

    expect(screen.getAllByText("Analyzing query…").length).toBeGreaterThan(0);
    expect(screen.getByText("Decomposing question")).toBeInTheDocument();
    expect(screen.getByText("Searching indices")).toBeInTheDocument();

    const toggle = screen.getByRole("button");
    fireEvent.click(toggle);
    fireEvent.click(toggle);
  });

  it("renders settled state when working is false", () => {
    render(
      <ThoughtLine
        working={false}
        doneLabel="Thought for"
        showTimer={false}
        steps={["Finished"]}
      />,
    );

    expect(screen.getAllByText("Thought for").length).toBeGreaterThan(0);
  });

  it("renders with dot glyph and custom renderLabel", () => {
    render(
      <ThoughtLine
        glyph="dot"
        renderLabel={(text) => <em>{text}</em>}
        steps={["Step 1", "Step 2"]}
        elapsed={70}
        collapsible={false}
      />,
    );
    expect(screen.getByText("Step 1")).toBeInTheDocument();
  });

  it("handles non-collapsible and none glyph", () => {
    render(
      <ThoughtLine
        glyph="none"
        collapsible={false}
        working={false}
        settleAfter={0.1}
      />,
    );
    expect(screen.getAllByText("Thought for").length).toBeGreaterThan(0);
  });

  it("runs interval timer and supports zero breath depth without shimmer", () => {
    vi.useFakeTimers();
    render(
      <ThoughtLine
        working={true}
        breathDepth={0}
        shimmer={false}
        settleAfter={0.2}
      />,
    );
    vi.advanceTimersByTime(300);
    vi.useRealTimers();
  });
});
