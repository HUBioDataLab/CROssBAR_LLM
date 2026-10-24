# ADR-006 — `score == 1.0` is a sentinel, not a perfect match

**Status:** Accepted — 2026-08-10, provisionally (may be rolled back after feedback on the
first delivery). Amends ADR-001 step 4; `select` implements the amended ranking.

## Context

ADR-001 left score semantics as an open question and ranked article groups by the **maximum
sentence score within the group**. The captured fixtures now explain what the scores are, and
the explanation breaks that ranking rule.

For both real queries, with `rerank=true`:

- Positions 0–92 carry scores in strictly descending order, roughly 0.76 down to 0.53.
- Positions 93–99 carry a score of exactly `1.0`.

The `1.0` values are a **trailing block**, appended after every scored hit. They are not the best
matches; they are the ones the reranker did not score. Two further observations confirm it:
with `rerank=false` **all 100** hits score exactly `1.0`, and the deliberately nonsensical query
— whose result set the reranker scored end to end — contains **no** `1.0` at all, just a
descending run from 0.55 to 0.40.

So the field means "the reranker's score, or `1.0` where there isn't one."

Ranking groups by max score would therefore have promoted precisely the unranked tail to the top
of the answer: seven of the hundred hits, sorted first. On the TP53 query, five of those seven
are `DISCUSS` sentences that the reranker declined to score, and they would have displaced
genuinely top-ranked abstracts. This is a silent relevance inversion — the pipeline would have
run, produced fluent cited answers, and been wrong about which evidence mattered.

## Decision

**`UNSCORED_SENTINEL = 1.0`, and `SentenceHit.is_unscored` names the condition.** No code
compares a raw score to `1.0`.

**`select` ranks unscored hits last, never first.** A group's rank key becomes:

1. the maximum score among its **scored** hits (a group with none is ranked below every group
   that has one);
2. hit count, as before;
3. first appearance in the response, as before.

Unscored hits are not dropped. They still travel into the context as matched sentences for a
group that earned its place on other evidence — the reranker declining to score a sentence is
not evidence the sentence is irrelevant.

**`min_score` stays `None`, and is now documented as unusable with `rerank=false`**, where every
hit would clear any floor below 1.0. If it is ever set, it applies to scored hits only.

**Scores remain within-response only.** Nothing here licenses comparing scores across queries.

## Rationale

The alternative reading — that `1.0` marks exact matches — is refuted by three independent
observations: the values sit at the end of a descending list rather than the start, they appear
for every hit when reranking is off, and they vanish entirely when the reranker scores the whole
set. Treating them as top matches is the one interpretation the data rules out.

Ranking rather than dropping keeps the change minimal and reversible. We do not know *why* the
reranker skips these sentences, and discarding evidence on the strength of a guess about an
undocumented field would be a larger bet than the one this ADR makes.

## Consequences

- ADR-001's "rank groups by max-of-group score" now reads "max-of-group score among scored
  hits". The rest of ADR-001 stands unchanged.
- `rerank=false` degrades to whatever order the API returns, since it supplies no scores at all.
  That is acceptable — `rerank` defaults to `True`, and this ADR is the reason to leave it there.
- Three tests in `tests/test_models.py` pin the sentinel's shape. If NCBI starts scoring the
  tail, they fail and this ADR gets revisited.
- The 7-of-100 figure is from two queries. Worth re-measuring across more queries before we
  treat the proportion as stable; the *interpretation* does not depend on it.
