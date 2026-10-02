# ADR-001 — Article selection from sentence-level results

**Status:** Accepted — step 4 of the decision is amended by ADR-006, which found that
`score == 1.0` marks an *unscored* hit. Ranking by max-of-group must ignore those, or the
unranked tail sorts to the top.

## Context

The task specifies "return N articles" from the sentence search endpoint. The endpoint does not
return articles. It returns a flat list of up to 100 sentences, each carrying a `pmid`/`pmcid`
pair, a `score`, and the section it came from. The same publication appears in multiple entries.

There is no API parameter that controls how many *distinct publications* come back. That
aggregation has to happen on our side, and how we do it directly determines which evidence the
LLM ever sees.

Complicating factors observed in live responses:

- `pmid` may be `null` (PMC-only records).
- `score` ordering under `rerank=true` is not cleanly monotonic and contains a tail of exact
  `1.0` values. We do not currently understand what that means.

## Decision

`select` is a **pure function** over the raw hit list, running in this order:

1. Drop hits where `pmid` is `null`.
2. Apply `min_score` if configured.
3. Group remaining hits by `pmid`.
4. Rank groups by the **maximum sentence score within the group**, tie-broken by hit count,
   then by first appearance in the response.
5. Take the top `max_articles` groups.
6. Carry the matched sentences forward alongside each pmid.

The matched sentences travel with the article into the synthesis context, not just the pmid.
They are the reason the article was retrieved and they cost almost nothing to include.

Until `score` semantics are understood, scores are used **only for within-response ordering** —
never as an absolute relevance threshold in defaults, never compared across queries. `min_score`
stays `None` by default.

## Rationale

- Max-of-group rather than mean: one highly relevant sentence is a strong signal, and averaging
  penalizes publications that happen to match on several weaker sentences.
- Pure function: this is where retrieval quality is decided, so it must be testable against
  fixtures without network or LLM calls.
- Dropping `pmid: null` records: the task requires PubMed IDs as references and the publication
  endpoint is keyed by pmid. A record we can neither fetch nor cite has no path into the answer.

## Consequences

- We silently lose PMC-only content. Acceptable for v1; revisit if fixtures show it's a large
  fraction of hits. Log the drop count so we can measure it.
- Requesting fewer than 100 sentences increases the risk that `max_articles` cannot be filled.
  Default `top_k_sentences` stays at the API maximum.
- If `score` turns out to be meaningful in a way we're not exploiting, this ADR gets revised —
  ranking is isolated in one function specifically so that revision is cheap.
