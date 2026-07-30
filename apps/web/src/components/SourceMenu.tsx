import { Check, FileText, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

type SourceOption = {
  id: string;
  label: string;
};

type Props = {
  options: SourceOption[];
  selected: string[];
  disabled?: boolean;
  onChange: (selected: string[]) => void;
};

export function SourceMenu({ options, selected, disabled = false, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <div className="source-menu" ref={rootRef}>
      <button
        className="source-menu-trigger"
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => {
          setOpen((current) => !current);
        }}
      >
        <FileText size={16} />
        <span>{selected.length ? `${String(selected.length)} sources` : "All sources"}</span>
      </button>
      {open ? (
        <div className="source-menu-popover" role="dialog" aria-label="Source documents">
          <div className="source-menu-heading">
            <div>
              <strong>Source documents</strong>
              <span>{selected.length ? "Only selected documents" : "Searching all documents"}</span>
            </div>
            <button
              className="source-menu-close"
              type="button"
              aria-label="Close source selector"
              onClick={() => {
                setOpen(false);
              }}
            >
              <X size={16} />
            </button>
          </div>
          {options.length ? (
            <div className="source-menu-options">
              <button
                className="source-menu-all"
                type="button"
                onClick={() => {
                  onChange([]);
                }}
              >
                <span>Search all documents</span>
                {!selected.length ? <Check size={16} /> : null}
              </button>
              {options.map((option) => {
                const checked = selected.includes(option.id);
                return (
                  <label key={option.id}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        onChange(
                          event.target.checked
                            ? [...selected, option.id]
                            : selected.filter((id) => id !== option.id),
                        );
                      }}
                    />
                    <span>{option.label}</span>
                  </label>
                );
              })}
            </div>
          ) : (
            <p className="source-menu-empty">No indexed sources yet.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
