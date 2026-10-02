import { motion } from "motion/react";
import React, { useId } from "react";

export type SegmentedItem<T extends string> = {
  value: T;
  label: React.ReactNode;
};

export interface SegmentedControlProps<T extends string> {
  label?: string;
  value: T;
  options: readonly (T | SegmentedItem<T>)[];
  onChange: (value: T) => void;
  size?: "sm" | "default";
  className?: string;
}

export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
  size = "default",
  className = "",
}: SegmentedControlProps<T>) {
  const instanceId = useId();

  const normalizedOptions: SegmentedItem<T>[] = options.map((opt) => {
    if (typeof opt === "string") {
      const formatted = opt.charAt(0).toUpperCase() + opt.slice(1).replace(/_/g, " ");
      return { value: opt, label: formatted };
    }
    return opt;
  });

  return (
    <div
      className={`segmented-control ${size === "sm" ? "segmented-control-sm" : ""} ${className}`}
      role="group"
      aria-label={label}
    >
      {normalizedOptions.map((option) => {
        const isSelected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={isSelected}
            onClick={() => {
              if (!isSelected) onChange(option.value);
            }}
            className={`segmented-control-btn${isSelected ? " is-active" : ""}`}
          >
            {isSelected && (
              <motion.span
                layoutId={`segmented-pill-${instanceId}`}
                className="segmented-active-pill"
                transition={{ type: "spring", stiffness: 450, damping: 35 }}
                aria-hidden="true"
              />
            )}
            <span className="segmented-btn-content">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default SegmentedControl;
