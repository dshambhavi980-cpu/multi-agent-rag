import { renderHook } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { useTheme } from "./theme-context";

describe("theme-context", () => {
  test("returns default fallback values when rendered outside ThemeProvider", () => {
    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("system");
    expect(result.current.resolvedTheme).toBe("light");
    expect(typeof result.current.setTheme).toBe("function");
    expect(typeof result.current.toggleTheme).toBe("function");

    // Calling the fallback functions should be safe and no-op
    expect(() => {
      result.current.setTheme("dark");
    }).not.toThrow();
    expect(() => {
      result.current.toggleTheme();
    }).not.toThrow();
  });
});
