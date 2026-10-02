# ADR-004 — Deferring the LLM provider and the delivery interface

**Status:** Accepted

## Context

Two decisions are genuinely open: which LLM provider to use, and whether the deliverable is a
CLI, an HTTP service, or a notebook demo. Neither needs to be settled to start building, and
guessing wrong on either would be expensive to unwind if the guess leaks into the codebase.

## Decision

**Provider.** All model access goes through `llm.py`, a single factory around
`init_chat_model(config.model)` where `model` is a provider-qualified string
(`anthropic:claude-...`, `openai:gpt-...`, `ollama:...`). No provider SDK is imported anywhere
else. No provider-specific parameters appear in node code. Switching providers is an
environment variable.

The one hard requirement on any candidate provider: **reliable structured output** (see
ADR-003). A model that can't be trusted to return a well-formed `Answer` object is disqualified
regardless of other merits.

**Interface.** The system is built as a library. The public surface is:

```python
async def answer_question(question: str, config: Settings) -> Answer: ...
```

The CLI is a thin argument-parsing wrapper. No orchestration, formatting decisions, or error
handling logic lives in `cli.py` that couldn't be reused by an HTTP handler. If a FastAPI
service is needed later, it calls the same function and the graph is untouched.

## Rationale

Both deferrals cost close to nothing structurally — a factory module and a function boundary —
and both are standard practice anyway. The alternative is either blocking work on decisions that
don't need making yet, or hardcoding an assumption that gets tangled through the codebase.

## Consequences

- A small amount of indirection that will look unnecessary if the provider never changes.
  Accepted.
- Provider-specific tuning (extended thinking, prompt caching, structured-output quirks) has one
  place to live and stays out of the pipeline.
- When either decision is made, record it here as an amendment rather than a new ADR.
