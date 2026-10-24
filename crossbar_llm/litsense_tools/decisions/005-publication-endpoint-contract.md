# ADR-005 — The publication endpoint as it actually behaves

**Status:** Accepted — 2026-08-10, provisionally: the first delivery is going out for external
feedback, and this decision may be rolled back with it. `client.py` implements it and changes
with it.

## Context

Build order step 1 required pinning `publication/{pmid}` down empirically before any code
depended on it. `scripts/explore_api.py` captured the responses now in `tests/fixtures/`;
`scripts/analyze_fixtures.py` re-derives everything below from them. Four observations change
what we can build.

**1. The response is a BioC document.** Top level: `_id`, `id`, `infons` (always `{}`),
`passages`, `relations`, `relations_display`, `pmid`, `pmcid`, `meta` (always `{}`), `date`
(ISO 8601), `journal`, `authors` (list of strings). The text lives in `passages[].text`, and the
section name lives in `passages[].infons.type`.

**2. There is no full text — ever.** Every document sampled contained exactly two passages,
`title` then `abstract`. That held for nine publications, including six chosen specifically
because a retrieved sentence came from their `METHODS`, `RESULTS`, `INTRO` or `DISCUSS` section
and because they carry a PMC id. LitSense indexes sentences from full text it will not serve
back through this endpoint.

**3. The `section` query parameter does nothing.** `?section=abstract`, `?section=methods` and
`?section=not_a_real_section` returned byte-identical 22,083-byte documents. Section selection
is entirely client-side.

**4. Errors do not follow HTTP conventions.** A pmid that does not resolve returns **500** with
`{"detail": "Can not retrieve publications : Publication not found"}`. A non-numeric path
segment returns 404 with `{"detail": "This resource is not available"}`. The permanent condition
is the one dressed as a server error.

Two smaller notes: top-level `pmcid` was `null` on every document, including articles that
plainly are in PMC — the PMC id hides in the title passage's `infons["article-id_pmc"]`. And a
publication with no abstract still returns an `abstract` passage, with `text` set to the empty
string (pmid 1).

## Decision

**Section selection is ours.** The client requests `publication/{pmid}` with no parameters and
`Publication.section_text(section)` filters passages on `infons.type`, case-insensitively.

**`section` is documented as effectively binary.** `abstract` and `title` are the only values
this endpoint can satisfy. The knob stays in `Settings` — it costs nothing and it is where the
value belongs — but `CLAUDE.md` and `.env.example` now say that anything else yields no text.
Reaching real full text means a different API (PMC BioC) and is out of scope for v1.

**Absent and empty are the same thing.** `section_text` returns `None` for a missing passage and
for a present-but-empty one. Callers get one "there is nothing here to ground an answer in"
condition, not two.

**Error mapping happens in `client.py`, by body and not by status alone.** A 500 from the
publication endpoint whose JSON `detail` contains `Publication not found` raises
`PublicationNotFound` and is **never retried**. Any other 500 keeps the ADR-002 retry
behaviour. 404 also raises `PublicationNotFound`.

**Retrieval-side metadata wins over document-side.** The pmcid a hit carries in the search
response is more reliable than the document's top-level `pmcid`, which is always null.

## Rationale

The retry rule is the part that matters. ADR-002 says "retry on 5xx" and, taken literally
against this API, ten unresolvable pmids in a fan-out become forty requests against a service
that rate limits us at one per second — thirty of them guaranteed to fail again. Body-sniffing a
500 is unpleasant, and it is still the right call: the alternative is punishing a service we are
a guest on for our own inability to read its response.

Collapsing absent and empty avoids a distinction with no consumer. Nothing downstream would ever
branch differently on "the abstract passage exists but is empty."

## Consequences

- The `section` knob is nearly decorative in v1. Documented rather than removed, so the day a
  full-text source is wired in there is nothing to re-plumb.
- `client.py` inspects response bodies to classify errors, which couples it slightly to
  NCBI's error strings. If they reword the message we degrade to retrying a permanent failure
  three times and then reporting it as unavailable — noisy, not wrong. The string check is in
  one place and there is a fixture pinning it.
- `Passage.annotations` and `relations` are captured in fixtures but deliberately not modelled.
  Admitting rich PubTator objects into the type would invite v1 code to start using them.
