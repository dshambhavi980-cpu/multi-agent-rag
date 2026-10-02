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
