import { ExternalLink, FileSearch, LoaderCircle, X } from "lucide-react";
import { useEffect, useState } from "react";

import { API_BASE_URL } from "../../api/client";
import type { Citation } from "./chat.types";

type Props = {
  citation: Citation;
  accessToken: string;
  workspaceId: string;
  onClose: () => void;
};

export function SourceViewer({ citation, accessToken, workspaceId, onClose }: Props) {
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    const load = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}${citation.source_url}`, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
            "X-Workspace-ID": workspaceId,
          },
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Source unavailable");
        objectUrl = URL.createObjectURL(await response.blob());
        setSource(
          citation.page ? `${objectUrl}#page=${String(citation.page)}` : objectUrl,
        );
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    };
    void load();
    return () => {
      controller.abort();
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [accessToken, citation, workspaceId]);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [onClose]);

  return (
    <div
      className="source-overlay"
      role="presentation"
      onMouseDown={() => {
        onClose();
      }}
    >
      <aside
        className="source-viewer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-title"
        onMouseDown={(event) => {
          event.stopPropagation();
        }}
      >
        <div className="source-heading">
          <div>
            <p className="eyebrow">Evidence {citation.citation_id}</p>
            <h2 id="source-title">{citation.label}</h2>
          </div>
          <button className="icon-button" type="button" aria-label="Close source" onClick={onClose}>
            <X size={19} />
          </button>
        </div>
        <blockquote className="source-quote">{citation.quote}</blockquote>
        <div className="source-document">
          {!source && !error ? (
            <div className="source-state">
              <LoaderCircle className="spin" size={22} />
              <span>Loading protected source...</span>
            </div>
          ) : null}
          {error ? (
            <div className="source-state source-state-error">
              <FileSearch size={22} />
              <span>The protected source could not be opened.</span>
            </div>
          ) : null}
          {source ? (
            <>
              <iframe title={citation.label} src={source} />
              <a href={source} target="_blank" rel="noreferrer">
                <ExternalLink size={15} /> Open source in a new tab
              </a>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
