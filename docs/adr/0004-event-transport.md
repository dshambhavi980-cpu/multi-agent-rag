# ADR 0004: Separate Run Streaming From Durable Status Updates

Status: Accepted  
Date: 2026-07-27

## Context

Token streaming and durable background status have different delivery needs.
Using one channel for both complicates reconnect and persistence semantics.

## Decision

Use authenticated Server-Sent Events from FastAPI for live answer tokens and
run events. Use Supabase Realtime for durable ingestion and approval record
changes. Every SSE event includes an event identifier and run sequence number.

SSE is a presentation stream, not the source of truth. Durable state remains in
PostgreSQL and can be fetched after reconnect.

## Consequences

- Browser implementation is simpler than bidirectional WebSockets.
- Reconnect can use `Last-Event-ID` and a run snapshot.
- Render process loss may interrupt a stream, but durable state remains.
- Realtime policies must follow the same workspace authorization boundary.
