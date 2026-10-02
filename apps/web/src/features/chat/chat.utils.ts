export function normalizeMarkdownContent(raw: string): string {
  // Pass 1: Standard or semi-broken markdown links like [alt](url) or alt](url) or ![alt](url)
  // where url is any URL containing document-assets or supabase.co/storage
  let healed = raw.replace(
    /(?:^|\s|\n)(!?\[([^\]]*)\]|[a-zA-Z0-9_\-\s]+\])\s*\(\s*((?:https?:\/\/)?[^\s)]+(?:\/document-assets\/|\.?supabase\.co\/storage\/)[^\s)]+)\)/g,
    (_match, bracketGroup: string, altFromBracket: string | undefined, rawUrl: string) => {
      let alt = (altFromBracket !== undefined ? altFromBracket : bracketGroup.replace(/\]$/, "")).trim();
      if (!alt || alt.toLowerCase().startsWith("in this")) {
        alt = "Architecture Diagram";
      }
      let url = rawUrl.trim();
      if (!/^https?:\/\//i.test(url)) {
        url = `https://${url}`;
      }
      return `\n\n![${alt}](${url})\n\n`;
    },
  );

  // Pass 2: Standalone or broken parentheses Supabase storage or document-assets image URLs, e.g.:
  // (supabase.co/storage/.../fig_p62_1.jpeg) [C1]
  // supabase.co/storage/.../fig_p62_1.jpeg)
  // (https://xyz.supabase.co/storage/.../fig_p62_1.jpeg) [C1]
  // xyz.supabase.co/storage/.../fig_p62_1.jpeg [C1]
  healed = healed.replace(
    /(?<!\])\s*\(?((?:https?:\/\/)?(?:[a-zA-Z0-9_\-\.]+\.)?supabase\.co\/storage\/[^\s)\]]+?|[^\s()\[\]]+\/document-assets\/[^\s()\[\]]+?)\)?(?=[.,;]?(\s|\[C[1-9]|$))/g,
    (match, rawUrl: string, _after: string, offset: number, fullStr: string) => {
      const prefix = fullStr.slice(Math.max(0, offset - 4), offset);
      if (prefix.includes("]")) {
        return match;
      }
      let url = rawUrl.replace(/[).,;]+$/, "").trim();
      if (!/^https?:\/\//i.test(url)) {
        url = `https://${url}`;
      }
      return `\n\n![Architecture Diagram](${url})\n\n`;
    },
  );

  return healed
    .replace(/\s+\*\s+(?=\*\*)/g, "\n* ")
    .replace(
      /\[(C[1-9][0-9]*)\]/g,
      (_match, citationId: string) => `[${citationId}](citation:${citationId})`,
    );
}

export function formatAgentStep(node: string): string {
  const lower = node.toLowerCase();
  if (lower.includes("retrieve") || lower.includes("search")) {
    return "Retrieval Agent: Slicing document pages and fetching vector matches";
  }
  if (lower.includes("rerank")) {
    return "Rerank Agent: Cross-encoding relevance and scoring passages";
  }
  if (lower.includes("verify") || lower.includes("citation")) {
    return "Citation Verifier: Grounding claims with original PDF coordinates";
  }
  if (lower.includes("synthes") || lower.includes("generate")) {
    return "Synthesis Agent: Generating grounded multimodal response";
  }
  return `Subagent: Executing ${node}`;
}
