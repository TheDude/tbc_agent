# Context Enrichment Agent — Design Document

> **Status:** Architectural design phase  
> **Last updated:** April 2026

---

## Overview

The context enrichment agent monitors team communications (emails, messages) and project artifacts, then surfaces relevant context to users when new information arrives. It also supports conversational queries, allowing users to ask for context surrounding communications they receive.

**Core capabilities:**
- Event-driven monitoring of incoming communications and artifacts
- LLM-driven reasoning to determine relevance and generate enriched summaries
- Conversational query interface for on-demand context lookups

---

## Architectural Principles

- **Prefer simplicity over framework weight.** The LLM handles internal reasoning, so heavyweight orchestration adds unnecessary complexity.
- **Strip down to what the use case requires.** Evaluate every dependency against actual needs.
- **Data sovereignty matters.** Prefer self-hosted tooling where feasible.
- **Debuggability is a first-class concern.** Intermediate steps (assembled prompts, raw LLM responses, tool call round-trips, state transitions) must be inspectable.

---

## Technology Stack

### Orchestration: Pydantic AI

**Selected over:** Burr, LangGraph, custom Python loop

**Rationale:**
- Lightweight — stays in pure Python without a heavy framework abstraction layer
- Structured I/O via Pydantic models; clean normalized event schema means the agent doesn't need to care whether a trigger was an email or a Slack message
- Tool dispatch and LLM calls handled natively
- The LLM handles internal reasoning, so a heavier orchestration framework adds no value

### Observability: Langfuse (SDK-direct)

**Selected over:** Arize Phoenix, LangSmith

**Integration approach:** Langfuse Python SDK directly (manual `langfuse.trace()` / `langfuse.span()` wrapping), rather than via OpenTelemetry.

**Rationale:**
- MIT-licensed; strong data sovereignty story
- Self-hosted (multi-container deployment)
- Direct SDK gives more control over what gets traced

**Key observability targets:**
- Assembled prompts sent to the LLM
- Raw LLM responses
- Tool call round-trips
- State transitions at checkpoints

### State Persistence: Flat JSON File

**Selected over:** SQLite, PostgreSQL, Redis, TinyDB

**Rationale:**
- The state problem here is primarily event deduplication — "have I processed this event before?" — not complex relational queries
- A flat JSON dict of processed event IDs with success/failure status is functionally sufficient for current scale
- Zero dependencies, zero ops overhead
- Natural migration path: if the memory system later lands on Postgres, consolidate there
