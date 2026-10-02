import { ExternalLink, FileSearch, LoaderCircle, X } from "lucide-react";
import { useEffect, useState } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

import { API_BASE_URL } from "../../api/client";
import { normalizeMarkdownContent } from "./ChatPage";
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
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [onClose]);

  const markdown = normalizeMarkdownContent(citation.quote);

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
              {citation.page ? ` • Page ${citation.page}` : ""}
              {citation.section ? ` • ${citation.section}` : ""}
            </p>
            <h2 id="source-title">{citation.label}</h2>
          </div>
          <div className="source-heading-actions">
            <button className="icon-button" type="button" aria-label="Close source" onClick={onClose}>
              <X size={19} />
            </button>
          </div>
        </div>

        <div className="source-quote">
          <div className="message-markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkBreaks]}
              urlTransform={(url) =>
                url.startsWith("citation:") ? url : defaultUrlTransform(url)
              }
              components={{
                img: ({ src, alt }) => {
                  if (!src) return null;
                  return (
                    <span className="chat-figure" role="figure">
                      <img
                        src={src}
                        alt={alt ?? "Architecture diagram"}
                        className="chat-embedded-image"
                        loading="lazy"
                        onClick={() => setPreviewImage(alt ? { src, alt } : { src })}
                      />
                      {alt ? <span className="chat-figure-caption">{alt}</span> : null}
                    </span>
                  );
                },
                a: ({ href, children }) => (
                  <a href={href} target="_blank" rel="noreferrer">
                    {children}
                  </a>
                ),
              }}
            >
              {markdown}
            </ReactMarkdown>
          </div>
        </div>

        <div className="source-document">
          {!source && !error ? (
            <div className="source-state">
              <LoaderCircle className="spin" size={16} />
              <span>Loading protected source...</span>
            </div>
          ) : null}
          {error ? (
            <div className="source-state source-state-error">
              <FileSearch size={16} />
              <span>The protected source could not be opened.</span>
            </div>
          ) : null}
          {source ? (
            <>
              <iframe title={citation.label} src={source} className="source-iframe" />
              <a href={source} target="_blank" rel="noreferrer" className="source-open-tab-link">
                <ExternalLink size={15} /> Open source in a new tab
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
          onClick={() => setPreviewImage(null)}
        >
          <div className="chat-lightbox-content" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              className="chat-lightbox-close"
              onClick={() => setPreviewImage(null)}
              aria-label="Close image preview"
            >
              <X size={20} />
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
