# ADR 0001: Use a Free Hosted Stack With Explicit SLO Limits

Status: Accepted  
Date: 2026-07-27

## Context

The first release must be publicly hostable without a paid subscription while
remaining structured for a later production infrastructure upgrade.

## Decision

Use Cloudflare Pages for React, Render Free for FastAPI, Supabase Free for the
data platform, Gemini's available free tier for generation and embeddings, and
GitHub Actions for CI.

Application code will use provider adapters and configuration-based model names.
Warm-path latency is an engineering objective. Render cold-start latency is
reported separately and is not represented as an always-on SLO.

## Consequences

- The portfolio deployment costs zero within provider limits.
- Render cold starts and provider quotas reduce availability.
- Public or synthetic documents must be used in the free demo.
- Moving to paid infrastructure should replace adapters/configuration rather than
  domain logic.
