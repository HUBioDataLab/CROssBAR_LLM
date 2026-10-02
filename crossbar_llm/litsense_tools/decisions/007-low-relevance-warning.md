# ADR-007 — A low-relevance warning, because the API never returns nothing

**Status:** Accepted — 2026-08-10. Requested by the project owner after dry-run exploration;
the threshold's default is provisional (evidence base: three captured queries).

## Context

The owner ran a deliberately nonsensical query through `--dry-run` and got ten fetched
articles with no complaint from the system. Their expectation — reasonable from the outside —
was an error or at least a warning.

The behaviour has a documented cause: LitSense **never returns an empty result**. A nonsense
query produces the same full page of 100 hits as a real one; the only externally visible
difference is the score distribution. Observed across the captured queries: real questions
peak at 0.74–0.76, the nonsense query at 0.548. The pipeline currently reads scores only for
*within-response ordering* — ADR-001 explicitly forbids using them as absolute relevance
thresholds in defaults, and ADR-006 reaffirmed that scores are not comparable across queries.

So the system was working as specified, and the specification was missing a signal the owner
needs: "this retrieval looks like noise."

## Decision

**A warning, not an error, and no filtering.** `relevance_warning(hits, threshold)` — a pure
function in `graph/nodes.py` — fires when the best *scored* hit falls below
`Settings.low_relevance_score` (default **0.6**, `None` disables). The warning is prepended to
the answer's `warnings` and shown in the dry-run report body. Selection, fetching and
synthesis proceed unchanged.

**This is the one sanctioned exception to "no absolute score comparison across queries."**
It is advisory: the cost of a false positive is one spurious warning line, not lost evidence.
`min_score` remains the tool for actually filtering, and remains off by default.

**The LLM stage keeps the final word.** `insufficient_context` from the model (or the
zero-article short-circuit) is still the authoritative "this cannot be answered" signal; the
warning exists because dry-run has no LLM and because a grounded-looking answer built on
uniformly weak evidence deserves a flag even when the model does answer.

**With `rerank=false` the warning cannot fire** — nothing is scored. Documented, not worked
around.

## Rationale

An *error* would violate invariant 6 (zero or weak evidence is a valid outcome, not a crash)
and would guess wrong sometimes: a threshold this thinly evidenced must not gate the
pipeline. A warning converts the one signal the API does emit — a depressed score ceiling —
into something a human sees without staring at score columns.

Why 0.6: midway between the observed nonsense ceiling (0.548) and the observed real-question
ceiling (0.739+), on three data points. That is thin, and it is the reason the knob exists
and the reason this ADR marks the default provisional.

## Consequences

- Real questions whose best evidence is genuinely weak will also trip the warning. That is
  the desired behaviour — the warning describes the retrieval, not the question's legitimacy.
- The 0.6 default should be revisited once more queries have been observed; the fixtures and
  `scripts/analyze_fixtures.py` are the place to re-derive it.
- If NCBI changes the reranker's score scale, the warning silently mis-calibrates. Accepted:
  it is advisory, and the fixture-pinned tests would catch a scale change indirectly.
