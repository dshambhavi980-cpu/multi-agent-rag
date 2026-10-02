import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { useTheme } from "./theme-context";
import { ThemeProvider } from "./ThemeProvider";

function TestConsumer() {
  const { theme, resolvedTheme, setTheme, toggleTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button type="button" onClick={() => { setTheme("dark"); }}>Set Dark</button>
      <button type="button" onClick={() => { setTheme("light"); }}>Set Light</button>
      <button type="button" onClick={() => { setTheme("system"); }}>Set System</button>
      <button type="button" onClick={() => { toggleTheme(); }}>Toggle</button>
    </div>
  );
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.className = "";
    document.documentElement.removeAttribute("data-theme");
  });

  test("initializes with default dark theme and responds to user selection", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    );

    expect(screen.getByTestId("theme")).toHaveTextContent("dark");
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");

    await user.click(screen.getByText("Set Light"));
    expect(screen.getByTestId("theme")).toHaveTextContent("light");
    expect(screen.getByTestId("resolved")).toHaveTextContent("light");
    expect(document.documentElement).not.toHaveClass("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(window.localStorage.getItem("docpilot:theme")).toBe("light");

    await user.click(screen.getByText("Toggle"));
    expect(screen.getByTestId("theme")).toHaveTextContent("dark");
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(window.localStorage.getItem("docpilot:theme")).toBe("dark");
  });

  test("loads existing theme from localStorage", () => {
    window.localStorage.setItem("docpilot:theme", "light");
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    );

    expect(screen.getByTestId("theme")).toHaveTextContent("light");
    expect(screen.getByTestId("resolved")).toHaveTextContent("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });

  test("handles matchMedia changes in system mode", () => {
    window.localStorage.setItem("docpilot:theme", "system");
    const listeners: ((e: MediaQueryListEvent) => void)[] = [];
    const descriptor = Object.getOwnPropertyDescriptor(window, "matchMedia");

    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn((event: string, handler: unknown) => {
          if (event === "change" && typeof handler === "function") {
            listeners.push(handler as (e: MediaQueryListEvent) => void);
          }
        }),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    );

    expect(screen.getByTestId("resolved")).toHaveTextContent("light");

    // Simulate OS switching to dark mode
    act(() => {
      for (const listener of listeners) {
        listener({ matches: true } as MediaQueryListEvent);
      }
    });

    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");
    expect(document.documentElement).toHaveClass("dark");

    if (descriptor) {
      Object.defineProperty(window, "matchMedia", descriptor);
    } else {
      delete (window as unknown as Record<string, unknown>).matchMedia;
    }
  });
});
