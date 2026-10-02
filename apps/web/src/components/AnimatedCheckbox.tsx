import { motion } from "motion/react";
import { HugeiconsIcon } from "@hugeicons/react";
import { Tick02Icon } from "@hugeicons/core-free-icons";
import React from "react";

export interface AnimatedCheckboxProps {
  checked: boolean;
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
  name?: string;
  value?: string;
  "aria-label"?: string;
  className?: string;
}

export function AnimatedCheckbox({
  checked,
  onChange,
  disabled = false,
  id,
  name,
  value,
  "aria-label": ariaLabel,
  className = "",
}: AnimatedCheckboxProps) {
  return (
    <span className={`inline-flex items-center justify-center select-none ${className}`}>
      <input
        type="checkbox"
        id={id}
        name={name}
        value={value}
        checked={checked}
        disabled={disabled}
        aria-label={ariaLabel}
        onChange={(e) => onChange?.(e.target.checked)}
        className="sr-only-checkbox"
      />
      <span
        aria-hidden="true"
        data-state={checked ? "checked" : "unchecked"}
        className="shadcn-checkbox"
      >
        {checked ? (
          <motion.span
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 500, damping: 30 }}
            className="flex items-center justify-center leading-none"
          >
            <HugeiconsIcon icon={Tick02Icon} size={11} strokeWidth={3} />
          </motion.span>
        ) : null}
      </span>
    </span>
  );
}

export default AnimatedCheckbox;
