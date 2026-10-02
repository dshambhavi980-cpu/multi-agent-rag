import { HugeiconsIcon } from "@hugeicons/react";
import { Moon02Icon, Sun01Icon } from "@hugeicons/core-free-icons";

import { useTheme } from "./theme-context";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { resolvedTheme, toggleTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  return (
    <button
      className={`icon-button theme-toggle ${className}`.trim()}
      type="button"
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      onClick={toggleTheme}
    >
      {isDark ? (
        <HugeiconsIcon icon={Sun01Icon} size={19} strokeWidth={1.8} aria-hidden="true" />
      ) : (
        <HugeiconsIcon icon={Moon02Icon} size={19} strokeWidth={1.8} aria-hidden="true" />
      )}
    </button>
  );
}
