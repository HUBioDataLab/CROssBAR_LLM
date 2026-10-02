# ADR-003 — Citation contract and grounding validation

**Status:** Accepted

## Context

The deliverable is not just an answer — it's an answer plus the PubMed IDs the answer was
actually built from. Those IDs are the entire trust story of the system. An LLM asked to append
references in prose will, sooner or later, produce a plausible-looking eight-digit number that
belongs to a paper about something else entirely. In a biomedical context that failure is worse
than no answer at all.

Two things can go wrong independently: the model cites something it wasn't given, and the model
answers from parametric knowledge while citing whatever happens to be in front of it. The first
is detectable. The second is not, mechanically — it has to be constrained by prompt design and
accepted as a residual risk.

## Decision

**Structured output, not prose parsing.** The synthesis node returns:

```python
class Answer(BaseModel):
    text: str
    citations: list[int]          # PubMed IDs
    insufficient_context: bool
    warnings: list[str] = []
```

Obtained via the model's structured-output binding. Under no circumstances do we regex PubMed
IDs out of generated prose.

**Context is presented with explicit pmid labels.** Each article block in the prompt is tagged
with its pmid so the model has an unambiguous handle to cite. The matched sentences from
retrieval are included alongside the section text.

**The prompt constrains the model to the provided context**, instructs it to set
`insufficient_context` rather than fill gaps from memory, and states that citing an ID not
present in the context is an error.

**`validate` runs after every synthesis.** It intersects `citations` with the set of pmids
actually fetched. IDs outside that set are dropped and a warning is appended. The node does not
retry and does not call the LLM — it is a pure function over state.

**Uncited answers are surfaced, not hidden.** If `citations` is empty while `text` makes
substantive claims, that gets a warning too.

## Rationale

Validation catches the detectable failure cheaply and deterministically. Structured output
removes an entire class of parsing bugs. Keeping `validate` pure and LLM-free means the safety
check can never itself hallucinate, and can be unit-tested exhaustively.

No retry on validation failure: this is a linear pipeline by design (see CLAUDE.md). A dropped
citation with a visible warning is more honest than a second roll of the dice.

## Consequences

- Validation proves a cited pmid **was retrieved**, not that it **supports the claim**. That
  stronger check needs per-claim entailment verification and is out of scope for v1. Do not
  describe the current system as verifying claim support.
- Requires a model with reliable structured-output support. Noted as a constraint on provider
  choice.
