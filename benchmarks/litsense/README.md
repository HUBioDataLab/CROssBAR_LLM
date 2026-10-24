# Benchmarks

Evaluation harness for the LitSense agent, mandated by supervisor feedback stage 2
(2026-08-18). Follows the structure of Ahmet Oğuzhan's PubTator3 harness: deterministic
token-overlap scoring always, LLM-as-judge optionally, headline hit rate / mean recall.

## Layout

| Path | What |
|---|---|
| `run.py` | The harness: questions → `LitSenseAgent` → scores → console summary + JSON |
| `metrics.py` | `overlap_score` (deterministic, unit-tested) + judge prompts/schema behind a seam |
| `report.py` | The **results contract** (per-question keys, per-mode aggregate, file layout; metric vocabulary = Ahmet Oğuzhan's, see `reference/paperclip_long.sample.json`) + the structured Markdown report per run folder + `--compare` across runs |
| `RESULTS-SCHEMA.md` | **Key glossary** for the result files — one line per key. Hand it to whoever reads the JSON |
| `models.json` | The multi-model comparison matrix (model id, reasoning level, provider order per row; the fixed judge) |
| `data/` | Benchmark question files (see registry in `run.py` for expected filenames) |
| `reference/` | Ahmet Oğuzhan's original `metrics.py`/`run.py` — **read-only prior art**, excluded from lint, never imported; they target his PubTator3/Paperclip agents and cannot run here. `paperclip_long.sample.json` is his real output trimmed to one question per dataset: the shape ours is pinned to (test) |
| `results/runs/<stamp>-<label>/` | **One folder per run**: `<dataset>.json` per dataset, `run.log`, `manifest.json`, `REPORT.md`. Runs never mix; the folder is written incrementally so a killed run keeps its finished datasets |
| `results/matrix/` | **The multi-model matrix in one folder**: every row's run folder under `runs/` (+ `pricing.json`) and the cross-model `COMPARISON.md` / `comparison.json` next to them (`litsense/scripts/run_model_matrix.py`) |
| `results/smoke/` | One-question verification runs of every matrix row (`launch --smoke`) |
| `results/legacy/` | Results of the pilot sets (crossbar, 10-question BioASQ, biohopr-40) from before 2026-09-15 — no longer part of the default report |

## Usage

```powershell
# No model, no key: retrieval runs for real, synthesis/gate are pass-through stubs.
uv run python -m litsense.run --dataset bioasq-factoid-100 --dry-run --n 5

# The standard run: the five active sets, both modes, judge — needs LITSENSE_MODEL + key.
# Lands in results/runs/<stamp>-gemini-2.5-flash/ (label = model short name, or --run-name).
uv run python -m litsense.run --dataset all --mode both --judge

# The Trello comparison: every question in abstracts AND full_text mode, side-by-side
# (hit rate, recall, judge score/informativeness/clarity, refinement counts, tokens, time).
# --answer-style bare asks the model for only the requested items (sharper overlap scores).
uv run python -m litsense.run --dataset bioasq-list --mode both --answer-style bare --judge

# Re-render a run folder's REPORT.md (done automatically at the end of every run), or
# build a report over arbitrary result files:
uv run python -m litsense.report litsense/results/runs/20260831-gemini-2.5-flash
uv run python -m litsense.report a.json b.json -o REPORT.md
```

Long runs: `--offset`/`--n` chunks each land in their own run folder;
`litsense/scripts/merge_benchmark_chunks.py OUT.json <chunk folders>/<dataset>.json …` stitches
them into one file you can drop into a run folder (then `report.py <run_dir>`).

**Results contract** (`report.py`; every key explained in `RESULTS-SCHEMA.md`). Per
dataset: `run_info` (model, reasoning, judge model, answer style, question slice, start),
`grounding_modes`, `results_by_grounding_mode` {`abstracts_only`, `full_text_refinement`}.
Per mode the flat aggregate: the reference harness's metric vocabulary verbatim
(`hit_rate`, `mean_recall`, `mean_judge`, `mean_informativeness`, `mean_clarity`, token
totals/means, elapsed totals), its two bare counters spelled out (`n_questions`,
`n_questions_answered`), then this harness's own (`retrieved_evidence_hit_rate` /
`_mean_recall`, `n_rejected_not_biomedical`, `n_refined_with_full_text`,
`n_answers_insufficient_context`, `n_questions_judged`, `n_questions_errored`, judge
token totals). Per question: `question_id`, `grounding_mode`, `question`,
`reference_answers`, `generated_answer`, `cited_pmids`, `answer_insufficient_context`,
`answer_warnings`, `error`, `elapsed_s`, then one block per pipeline stage
(`biological_relevance_check`, `sentence_search`, `publication_selection`,
`publication_fetch`, `full_text_refinement`), `entities_in_cited_publications`,
`answer_overlap` / `retrieved_evidence_overlap` {hit, recall, matched_items,
missed_items}, `llm_judge` {score, informativeness, clarity, matched_items,
missed_items, rationale}, `agent_tokens` / `judge_tokens` {input, output, reasoning,
cache_read, total, calls}. The names were spelled out on 2026-09-24 after team feedback
that the short ones (`n`, `per_mode`, `gate`, `search`, `fetch`, `depth`, …) did not
explain themselves; `normalize_results` lifts every older layout and key set, and
`report.py <run_dir> --rewrite` rewrites a folder permanently. Token usage is summed by
the agent over its own model calls (relevance check + synthesis + depth evaluator) via
a LangChain callback — no seam changes; the judge's own usage is recorded apart so the
agent totals stay comparable with the reference harness. Runs recorded before
2026-09-14 have zero tokens and show "—".

The harness scores **evidence and answer separately**: `retrieved_evidence_overlap` asks
whether the fetched titles/abstracts/matched sentences contain the reference items
(measures retrieval alone — meaningful without a model), `answer_overlap` scores the
generated answer (meaningful only with a real model; in dry-run the answer is a fixed
stub and its scores are noise — the stub's literal word "dry" even lexically matches
references like "dry skin").

## Datasets

| Name | File (in `data/`) | Kind | Status |
|---|---|---|---|
| `crossbar` | `CROssBAR_example_queries.json` | list | **Present.** No curated ground truth — references are provisional (see `reference_note` per item); mostly multi-hop KG questions probing the literature/KG boundary |
| `bioasq-factoid` | `BioASQ_10_selected_factoid_type_questions.json` | factoid | Present, run live 2026-08-29 |
| `bioasq-list` | `BioASQ_10_selected_list_type_questions.json` | list | Present, run live 2026-08-29 |
| `biohopr` | `BioHopR_selected_questions.json` | list | Present, run live 2026-08-31 |
| `bioasq-factoid-100`, `bioasq-list-100` | `factoid_subset.json`, `list_subset.json` | factoid / list | Present, run live 2026-08-31 |
| `biohopr-{disease-protein-drug, drug-protein-disease, protein-disease-drug}` | same names + `.json` | list | Present, run live 2026-08-31 |

**Active sets** (`--dataset all`, the default report): the five large ones. Their
2026-08-31 results are `results/runs/20260831-gemini-2.5-flash/` (no token data — that
run predates capture); the 2026-09-15 rerun with tokens is the gemini-2.5-flash baseline
row of the matrix (`results/matrix/runs/20260915-204848-gemini-2.5-flash/`). The pilot
sets' results are in `results/legacy/`.

## First results (2026-08-18, crossbar, dry-run — retrieval only)

`results/20260818-crossbar-dryrun.json`. Evidence hit rate **0.83**, mean recall **0.43**
over 6 questions. Highlights:

- Single-hop-ish questions retrieve well: pathways-in-two-diseases hit 6/6 reference items
  (recall 1.00), Alzheimer drugs 6/8 (0.75), EGFR side effects 6/13.
- The pure knowledge-graph question (shortest path MDM2→Sorafenib) retrieved nothing
  relevant (0/7) — exactly the boundary the reference notes predicted. Whether the
  relevance gate should *decline* KG-shaped questions as out-of-literature-scope is a
  question for the supervisor/meeting.
- The ALS-orthologs multi-hop question returned only **3 hits** from LitSense — by far the
  shortest page ever observed (previous minimum: 17). Long fluent multi-hop phrasing can
  shrink the page, not just rare vocabulary.
