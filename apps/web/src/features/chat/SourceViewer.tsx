import { HugeiconsIcon } from "@hugeicons/react";
import {
  ArrowExpand01Icon,
  Cancel01Icon,
  FileSearchIcon,
  LinkSquare01Icon,
  Loading03Icon,
} from "@hugeicons/core-free-icons";
import { useEffect, useState } from "react";

import { API_BASE_URL } from "../../api/client";
import type { Citation } from "./chat.types";

type SourceAccess = {
  url: string;
  expires_at: string;
};

const sourceCache = new Map<string, SourceAccess>();

function cachedSource(workspaceId: string, sourceUrl: string): string | null {
  const cached = sourceCache.get(`${workspaceId}:${sourceUrl}`);
  return cached && Date.parse(cached.expires_at) > Date.now() + 10_000
    ? cached.url
    : null;
}

type Props = {
  citation: Citation;
  accessToken: string;
  workspaceId: string;
  onClose: () => void;
};

export function SourceViewer({ citation, accessToken, workspaceId, onClose }: Props) {
  const [source, setSource] = useState<string | null>(() =>
    cachedSource(workspaceId, citation.source_url),
  );
  const [pagePreviewUrl, setPagePreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [previewImage, setPreviewImage] = useState<{ src: string; alt?: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const cacheKey = `${workspaceId}:${citation.source_url}`;
    if (cachedSource(workspaceId, citation.source_url)) {
      return () => {
        controller.abort();
      };
    }
    const load = async () => {
      try {
        const sourceUrlPath = citation.source_url.replace(
          /\/source(?=\?|$)/,
          "/source-url",
        );
        const response = await fetch(`${API_BASE_URL}${sourceUrlPath}`, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
            "X-Workspace-ID": workspaceId,
          },
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Source unavailable");
        const access = (await response.json()) as SourceAccess;
        sourceCache.set(cacheKey, access);
        setSource(access.url);
        setError(false);
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    };
    void load();
    return () => {
      controller.abort();
    };
  }, [accessToken, citation, workspaceId]);

  useEffect(() => {
    if (!citation.page) return;
    const docMatch = citation.source_url.match(/\/documents\/([0-9a-fA-F-]+)/);
    if (!docMatch) return;
    const documentId = docMatch[1] ?? "";
    const controller = new AbortController();

    const loadPreview = async () => {
      try {
        const q = encodeURIComponent(citation.quote.slice(0, 300));
        const p = String(citation.page ?? 1);
        const url = `${API_BASE_URL}/v1/documents/${documentId}/pages/${p}/preview?quote=${q}`;
        const res = await fetch(url, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
            "X-Workspace-ID": workspaceId,
          },
          signal: controller.signal,
        });
        if (res.ok) {
          const blob = await res.blob();
          setPagePreviewUrl(URL.createObjectURL(blob));
        }
      } catch {
        // Fallback to standard source view
      }
    };
    void loadPreview();
    return () => {
      controller.abort();
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
            <p className="eyebrow">
              Evidence {citation.citation_id}
              {citation.page !== null ? ` • Page ${String(citation.page)}` : ""}
              {citation.section ? ` • ${citation.section}` : ""}
            </p>
            <h2 id="source-title">{citation.label}</h2>
          </div>
          <div className="source-heading-actions">
            <button className="icon-button" type="button" aria-label="Close source" onClick={onClose}>
              <HugeiconsIcon icon={Cancel01Icon} size={19} strokeWidth={1.8} />
            </button>
          </div>
        </div>

        <div className="source-document">
          {pagePreviewUrl ? (
            <div className="source-page-preview-card">
              <div className="source-page-preview-bar">
                <span className="source-page-tag">
                  Page {String(citation.page ?? 1)} Scan • Highlighted
                </span>
                <button
                  type="button"
                  className="source-expand-btn"
                  onClick={() => {
                    setPreviewImage({
                      src: pagePreviewUrl,
                      alt: `Page ${String(citation.page ?? 1)} with highlighted citation`,
                    });
                  }}
                  title="Click to expand page in fullscreen"
                >
                  <HugeiconsIcon icon={ArrowExpand01Icon} size={13} strokeWidth={1.8} /> Fullscreen
                </button>
              </div>
              <div
                className="source-page-img-box"
                onClick={() => {
                  setPreviewImage({
                    src: pagePreviewUrl,
                    alt: `Page ${String(citation.page ?? 1)} with highlighted citation`,
                  });
                }}
              >
                <img
                  src={pagePreviewUrl}
                  alt={`Page ${String(citation.page ?? 1)} with highlighted citation`}
                  className="source-page-img"
                  loading="eager"
                />
                <div className="source-page-zoom-hint">Click to enlarge page</div>
              </div>
            </div>
          ) : null}

          {!source && !error && !pagePreviewUrl ? (
            <div className="source-state">
              <HugeiconsIcon icon={Loading03Icon} className="spin" size={16} strokeWidth={1.8} />
              <span>Loading PDF page scan...</span>
            </div>
          ) : null}
          {error && !pagePreviewUrl ? (
            <div className="source-state source-state-error">
              <HugeiconsIcon icon={FileSearchIcon} size={16} strokeWidth={1.8} />
              <span>The protected source could not be opened.</span>
            </div>
          ) : null}
          {source ? (
            <>
              <iframe
                title={citation.label}
                src={source}
                className={pagePreviewUrl ? "source-iframe hidden" : "source-iframe"}
              />
              <a href={source} target="_blank" rel="noreferrer" className="source-open-tab-link">
                <HugeiconsIcon icon={LinkSquare01Icon} size={15} strokeWidth={1.8} /> Open full document in a new tab
              </a>
            </>
          ) : null}
        </div>
      </aside>

      {previewImage ? (
        <div
          className="chat-lightbox-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Enlarged diagram"
          onClick={() => {
            setPreviewImage(null);
          }}
        >
          <div
            className="chat-lightbox-content"
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            <button
              type="button"
              className="chat-lightbox-close"
              onClick={() => {
                setPreviewImage(null);
              }}
              aria-label="Close image preview"
            >
              <HugeiconsIcon icon={Cancel01Icon} size={20} strokeWidth={1.8} />
            </button>
            <img
              src={previewImage.src}
              alt={previewImage.alt ?? "Diagram"}
              className="chat-lightbox-img"
            />
            {previewImage.alt ? (
              <p className="chat-lightbox-caption">{previewImage.alt}</p>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
