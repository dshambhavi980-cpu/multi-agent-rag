import { describe, expect, test } from "vitest";
import { formatAgentStep, formatConversationDisplay, normalizeMarkdownContent } from "./chat.utils";

describe("normalizeMarkdownContent", () => {
  test("preserves regular markdown text without changes", () => {
    const input = "This is a regular explanation with no assets or citations.";
    expect(normalizeMarkdownContent(input)).toBe(input);
  });

  test("transforms document-assets markdown images with provided alt text", () => {
    const input = "Check this architecture: ![System Overview](https://api.example.com/document-assets/diagram.png)";
    expect(normalizeMarkdownContent(input)).toContain("![System Overview](https://api.example.com/document-assets/diagram.png)");
  });

  test("heals malformed document-assets markdown links missing opening bracket", () => {
    const input = "Flow diagram: Cache Tier](https://api.example.com/document-assets/cache.png)";
    expect(normalizeMarkdownContent(input)).toContain("![Cache Tier](https://api.example.com/document-assets/cache.png)");
  });

  test("replaces generic 'in this' alt descriptions with fallback", () => {
    const input = "![in this figure we see database nodes](https://api.example.com/document-assets/db.png)";
    expect(normalizeMarkdownContent(input)).toContain("![Architecture Diagram](https://api.example.com/document-assets/db.png)");
  });

  test("replaces empty alt with Architecture Diagram", () => {
    const input = "![](https://api.example.com/document-assets/node.png)";
    expect(normalizeMarkdownContent(input)).toContain("![Architecture Diagram](https://api.example.com/document-assets/node.png)");
  });

  test("converts citation bracket markers into citation links", () => {
    const input = "Refer to [C1] and secondary source [C15].";
    expect(normalizeMarkdownContent(input)).toBe(
      "Refer to [C1](citation:C1) and secondary source [C15](citation:C15).",
    );
  });

  test("heals spaced bullet list markdown items", () => {
    const input = "Features:\n * **High Availability**\n * **Fault Tolerance**";
    expect(normalizeMarkdownContent(input)).toBe(
      "Features:\n* **High Availability**\n* **Fault Tolerance**",
    );
  });
});

describe("formatAgentStep", () => {
  test("formats retrieval step", () => {
    expect(formatAgentStep("retrieve")).toContain("Retrieval Agent");
    expect(formatAgentStep("search_index")).toContain("Retrieval Agent");
  });

  test("formats rerank step", () => {
    expect(formatAgentStep("rerank")).toContain("Rerank Agent");
  });

  test("formats verify step", () => {
    expect(formatAgentStep("verify")).toContain("Citation Verifier");
    expect(formatAgentStep("citation_check")).toContain("Citation Verifier");
  });

  test("formats synthesize step", () => {
    expect(formatAgentStep("synthesize")).toContain("Synthesis Agent");
    expect(formatAgentStep("generate_text")).toContain("Synthesis Agent");
  });

  test("formats default node step", () => {
    expect(formatAgentStep("custom_node")).toBe("Subagent: Executing custom_node");
  });
});

describe("formatConversationDisplay", () => {
  test("extracts document tag and formats title cleanly", () => {
    const res = formatConversationDisplay("@Shambhavi_Dubey_Resume.pdf describe my internship experience");
    expect(res.docName).toBe("Shambhavi_Dubey_Resume.pdf");
    expect(res.title).toBe("Describe my internship experience");
  });

  test("handles document tag with empty query text", () => {
    const res = formatConversationDisplay("@Manual.pdf");
    expect(res.docName).toBe("Manual.pdf");
    expect(res.title).toBe("Document discussion");
  });

  test("formats plain title without document tag", () => {
    const res = formatConversationDisplay("how does rate limiting work?");
    expect(res.docName).toBeNull();
    expect(res.title).toBe("How does rate limiting work?");
  });

  test("handles null or undefined title", () => {
    expect(formatConversationDisplay(null).title).toBe("Untitled conversation");
    expect(formatConversationDisplay(undefined).title).toBe("Untitled conversation");
  });
});
