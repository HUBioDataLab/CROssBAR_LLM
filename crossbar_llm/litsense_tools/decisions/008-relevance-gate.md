# ADR-008 — A relevance gate before retrieval, on supervisor instruction

**Status:** Accepted — 2026-08-18. Mandated by the supervisor (feedback stage 2, relayed via
Discord); mirrors the "biological relevance validation node" their team runs in the CROssBAR
LLM interface.

## Context

ADR-007 established that retrieval scores catch vocabulary gibberish but not fluent
absurdity: the owner's alligator question scored *above* the real TP53 query. The Known
unknowns concluded that no retrieval-level scalar separates fluent-absurd questions from
real ones, and that any pre-check layer would touch the linear-pipeline principle — so the
question was explicitly parked as the supervisor's call.

The supervisor has now made that call: their team added a biological relevance validation
node for nonsense queries — if the question is not relevant, it routes directly to END —
and instructed us to do the same. They also acknowledged the known limitation up front:
"your alligator question might still pass it, but it still serves as a filter."

## Decision

**An LLM-based gate on the question itself, before any retrieval.** A new `relevance` node
runs first when `Settings.relevance_gate` is true (the default): it sends the raw question
to the configured model with a dedicated prompt and gets back a structured
`RelevanceVerdict(relevant, reason)`. A negative verdict short-circuits to END with a
composed answer — `insufficient_context=True`, the verdict's reason in the text, and a
warning naming the gate — without a single HTTP request leaving the process.

**This is the one sanctioned conditional edge in the graph.** Everything after `search`
stays linear; there is still no query rewriting, no retrieval retry, no tool selection.
With the gate disabled the graph is built without the node and is fully linear again.

**The gate is a seam, like synthesis.** `RelevanceChecker` in `llm.py` has the same shape
as `Synthesizer` (async, messages in, validated model out), so the team's own LLM plugs in
behind it with one adapter, tests inject fakes, and `build_dry_run_relevance_checker()`
keeps the pipeline runnable with no model and no API key.

**Judge the question, not the answer.** The prompt instructs the model to pass anything
that is a coherent biomedical question — narrow, obscure, or likely unanswered included —
and to reject only what has no biomedical subject, no askable question, or is not a
literature question at all. When in doubt, let it through: the downstream
insufficient-context defence still exists.

## Rationale

The alternative — a retrieval-score gate — is known not to work (score ceilings overlap;
Known unknowns, 2026-08-10). An LLM reading the question is the only layer that can see
*sense* rather than vocabulary. Making it a hard gate rather than an ADR-007-style warning
is a deliberate trade the supervisor chose: their team runs the same design, and a filtered
nonsense question costs a re-phrase, while an unfiltered one costs a full retrieval run
(5–15s of NCBI budget) and a grounded-looking answer to garbage.

ADR-007 is unchanged: the score-ceiling warning still fires for questions that pass the
gate but retrieve weakly — the two layers catch different failures (the gate catches
non-questions; the warning catches real questions the literature does not address).

## Consequences

- One extra LLM call per question, before any retrieval. Latency cost is small against the
  4–9s search; token cost is one short prompt.
- False positives are possible and are the accepted cost of a hard gate: an exotic but real
  question could be rejected. Mitigations: the permissive prompt, the `reason` shown to the
  user, and `relevance_gate=False` to switch the node off entirely.
- Fluent absurdity that *names real biology* (the alligator question) may still pass —
  acknowledged by the supervisor. The LLM-stage insufficient-context defence remains the
  next line, and remains unverified live (queued follow-up #1).
- The gate needs a model. Retrieval-only dry runs must inject
  `build_dry_run_relevance_checker()` (or disable the gate), exactly as they already inject
  the dry-run synthesizer.
- `answer_question` / `run_pipeline` / `LitSenseAgent` grew a `relevance_checker` seam
  parameter; no existing call site breaks (default builds from `Settings.model`).
