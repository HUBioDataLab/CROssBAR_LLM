# Fixtures

Real responses captured from the live LitSense 2.0 API on 2026-08-06 by
`scripts/explore_api.py`. Unit tests read these and never touch the network.

To recapture, run `uv run python scripts/explore_api.py` (hits the live API, one request per
second) and then `uv run python scripts/analyze_fixtures.py` to re-derive the observations that
ADR-005 and ADR-006 rest on. `tests/test_models.py` will fail loudly if the contract moved.

| File | What it pins |
|---|---|
| `sentences_what_is_the_role_of_tp53_...json` | A real query, `rerank=true`. The reference fixture: 100 hits, 97 distinct pmids, 7 unscored `1.0` hits at positions 93–99 |
| `sentences_crispr_base_editing_off_target_effects.json` | A second real query. Has hits with `annotations: null` and `section: null` |
| `sentences_zzzqx_nonexistent_biomedical_concept_wibble.json` | A nonsense query. Still 100 hits, all scored, none above 0.55 — low relevance is a score, not an empty response |
| `sentences_rerank_false.json` | Same query as the reference, `rerank=false`. Every score is exactly `1.0`, which is what proves `1.0` is a sentinel |
| `publication_27863244.json` | A normal document: title + abstract, 33 authors, journal, date |
| `publication_39039912.json` | A second normal document, plus PMC id hiding in the title passage's `infons` |
| `publication_39039912_section_{abstract,methods,not_a_real_section}.json` | Byte-identical to the above — proof the `?section=` parameter is ignored |
| `publication_1_no_abstract.json` | The no-abstract case: an `abstract` passage whose `text` is `""` |
| `publication_unresolvable.json` | HTTP **500** `Can not retrieve publications : Publication not found` — a permanent failure with a retryable status |
| `publication_non_numeric.json` | HTTP 404 `This resource is not available` |
| `probes.json` | Status code, content type, latency and shape of every request made during capture. The status codes above are asserted from here |
