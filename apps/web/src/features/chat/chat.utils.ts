export function normalizeMarkdownContent(raw: string): string {
  const healed = raw.replace(
    /(?:^|\s|\n)(!?\[([^\]]*)\]|[a-zA-Z0-9_\-\s]+\])\((https?:\/\/[^\s)]+\/document-assets\/[^\s)]+)\)/g,
    (_match, bracketGroup: string, altFromBracket: string | undefined, url: string) => {
      let alt = (altFromBracket !== undefined ? altFromBracket : bracketGroup.replace(/\]$/, "")).trim();
      if (!alt || alt.toLowerCase().startsWith("in this")) {
        alt = "Architecture Diagram";
      }
      return `\n\n![${alt}](${url})\n\n`;
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
