# ADR-009 — Full text from BioC-PMC, behind a depth-refinement loop

**Status:** Accepted — 2026-08-18. Mandated by the team's Trello tasks (relayed by the
owner): a final-stage scientific-depth check that, on an insufficient verdict, goes back,
takes output from the full papers and rebuilds the answer; abstracts stay the default
unless the user says otherwise ("parametric").

## Context

The LitSense publication endpoint serves title + abstract only — verified, ADR-005 — so
"go back to the full papers" needs a second source. The known-unknowns list had already
flagged PMC BioC as the likely route; `scripts/explore_pmc.py` pinned it down live
(fixtures: `pmc_fulltext_*.json`, probe log: `pmc_probes.json`).

### Verified BioC-PMC facts (2026-08-18)

```
GET https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{pmcid}/unicode
```

- Returns a **list of BioC collections**; the article is `[0]["documents"][0]`. Passages
  carry the section in `infons.section_type` (uppercase: `TITLE`, `ABSTRACT`, `INTRO`,
  `METHODS`, `RESULTS`, `DISCUSS`, `CONCL`, plus non-narrative `FIG`, `TABLE`, `REF`,
  `SUPPL`, `AUTH_CONT`, `COMP_INT`) — not `infons.type` as on the LitSense endpoint.
- The `PMC` prefix is **required**: a bare numeric id returns the error page.
- **Errors are 200 + an HTML error page** (`[Error] : No result can be found.`), for
  invalid and unknown ids alike. Status codes are useless; the not-found signal is an
  unparseable/shapeless body. Detected in the client, raised as `FullTextNotFound`,
  never retried.
- All three probed fixture articles (including the paywalled Cell 2016 one, present as an
  author manuscript) returned full text, ~76–77K chars each including references.
- 81–94 of every 100 captured search hits carry a `pmcid`, so coverage is good; the
  pmcid comes from the retrieval-side hits (the publication document's own is always
  null, ADR-005).

## Decision

**Fetch:** `client.fetch_full_text(pmcid)` — same limiter, retry and cache patterns as the
other calls; absolute URL (the service lives outside the LitSense root, but the rate limit
belongs to NCBI as a whole, so the one shared limiter paces it too). `FullText.body()`
keeps only the narrative sections (`ABSTRACT INTRO METHODS RESULTS DISCUSS CONCL`) and
caps at `Settings.full_text_max_chars` per article (default 30K chars) — references and
figure scaffolding are noise at LLM prices, and the reference harness warned about 50K+
token prompts.

**Loop:** with `Settings.full_text=True`, after synthesis a `DepthEvaluator` (a seam with
the same shape as `Synthesizer` — the team's LLM plugs in identically;
`build_dry_run_depth_evaluator()` always accepts) judges the answer's scientific depth.
Insufficient → `refine`: the **cited** articles (all of them when nothing was cited) with
a pmcid get their abstract swapped for the narrative body, and synthesis runs once more.
Guards: exactly one refinement (`state.refined`); no re-evaluation after it (the verdict
stands); if refinement upgraded nothing (no pmcid, nothing in PMC), the first answer goes
straight to validation — no wasted second model call; fetch failures keep the abstract and
are reported in the answer's warnings, never fatal.

**Default:** `full_text=False` — answers come from abstracts, the depth node is not even
built, and the graph stays as it was. This is the Trello "parametric, abstracts unless the
user says otherwise" requirement.

## Rationale

Escalate-on-demand (abstracts first, full text only when a judge asks for it) is the shape
the team already runs in Ahmet Oğuzhan's PubTator3 agent (`evaluate_depth` + refinement),
and it spends full-text tokens only where a shallow answer proves it is needed. Bounding
to cited articles bounds cost by what the first answer actually used.

This is the second sanctioned departure from the linear pipeline (after ADR-008). Still
absent, deliberately: query rewriting, retrieval retries, tool selection.

## Consequences

- Refinement costs one extra LLM call (the evaluator), up to `max_articles` full-text
  fetches at 1 req/s, and one re-synthesis over much longer contexts.
- The depth evaluator needs a model; with `full_text=True` and no live model, inject
  `build_dry_run_depth_evaluator()` (benchmarks measuring the first-pass answer want it
  anyway).
- Articles refined to full text report `section="full_text"` in the answer's contexts.
- PMC coverage is not universal; articles without a pmcid or without PMC text silently
  keep their abstract (with a warning naming the failed pmcids).
- The `--mode both` benchmark comparison (abstracts vs full text, quality and cost) is now
  runnable once a model is connected — token accounting is still an open item, since usage
  capture has to live in the model adapter behind the `Synthesizer` seam.
