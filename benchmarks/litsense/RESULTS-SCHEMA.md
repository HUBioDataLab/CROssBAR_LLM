# Benchmark results — key glossary

Every benchmark run writes one JSON file per dataset into its run folder
(`litsense/results/runs/<YYYYMMDD-HHMMSS>-<label>/`, or `results/matrix/runs/…` for the
multi-model matrix). This page explains every key in those files so the numbers can be
read without the code. The file is `{"<dataset name>": <dataset block>}`.

The metric vocabulary (`hit_rate`, `mean_recall`, `mean_judge`, `mean_informativeness`,
`mean_clarity`, the token and elapsed totals, the judge's `score`/`matched_items`/
`missed_items`/`rationale`) is Ahmet Oğuzhan's, so both agents' numbers sit in the same
columns. Every other key was renamed on 2026-09-24 after team feedback that the previous
short names (`n`, `per_mode`, `gate`, `search`, `fetch`, `depth`, …) did not explain
themselves. `litsense/report.py` lifts files written with the old names automatically.

## Dataset block

| Key | Meaning |
|---|---|
| `run_info` | What produced the block: `harness`, `model` (provider-qualified model under test), `reasoning_effort` (requested reasoning level, `none` = explicitly off, `null` = provider default), `structured_output_method`, `provider_order` (OpenRouter upstream preference), `judge_model` (the LLM judge whose verdicts are in `llm_judge`; `null` when no judge ran), `judge_history` (present after a re-judge: the judges replaced, with timestamps), `answer_style` (`prose` = one consolidated paragraph, `bare` = only the requested items), `max_articles` (publications carried into the answer), `question_offset` / `question_limit` (which slice of the dataset ran; `null` limit = the whole file), `started`, `schema` (this file). |
| `grounding_modes` | The grounding modes this dataset was run in, in order (see below). |
| `results_by_grounding_mode` | One block per grounding mode: the aggregate keys below, then `per_question`. |

### Grounding modes

| Mode key | Meaning |
|---|---|
| `abstracts_only` | Every answer is grounded on the abstracts of the selected publications. The team default. |
| `full_text_refinement` | Abstracts first; then an LLM depth check judges the answer and, when it finds it insufficient, the cited publications' abstracts are swapped for their narrative full text (BioC-PMC, capped per article) and the answer is synthesised once more. At most one pass (ADR-009). |

A run made with `--mode both` runs every question in both modes, so the two blocks
are directly comparable question by question.

## Aggregate keys (one set per grounding mode)

Rates divide by every question run (an errored question counts as a miss); judge means
average over the questions the judge actually scored.

| Key | Meaning |
|---|---|
| `n_questions` | Questions run in this mode. |
| `n_questions_answered` | Questions for which the agent produced an answer text and no error was recorded. |
| `hit_rate` | Share of questions whose generated answer lexically contains at least one reference item (deterministic overlap, no LLM). Factoid sets: any synonym counts. |
| `mean_recall` | Mean over questions of (reference items found in the answer ÷ reference items). For factoid sets this equals the hit. |
| `mean_judge` | Mean LLM-judge correctness score, 0–5, over judged questions. |
| `mean_informativeness` | Mean LLM-judge informativeness, 0–5: how explanatory the answer is beyond the bare term, independent of correctness. |
| `mean_clarity` | Mean LLM-judge clarity, 0–5: how clearly the answer is presented, independent of correctness. |
| `total_tokens`, `mean_tokens` | Tokens spent by the agent's own model calls (relevance check + synthesis + depth evaluator), summed over the mode / per question. Reasoning tokens are included (providers bill them as output). |
| `total_input_tokens`, `total_output_tokens`, `total_reasoning_tokens` | The same, split. `mean_input_tokens`, `mean_output_tokens`: per question. |
| `total_elapsed_s`, `mean_elapsed_s`, `max_elapsed_s` | Wall-clock seconds per question (retrieval + model calls; the judge is not included). |
| `total_model_calls` | Number of agent model calls counted in the token totals. |
| `total_judge_tokens`, `mean_judge_tokens` | The judge's own token usage, kept apart from the agent totals so those stay comparable across harnesses. |
| `n_questions_judged` | Questions the judge scored. |
| `n_questions_errored` | Questions where the pipeline raised (recorded, the run continued). |
| `n_rejected_not_biomedical` | Questions the biological relevance check turned away before retrieval (ADR-008). |
| `n_refined_with_full_text` | Questions where the full-text refinement fired (only in `full_text_refinement` mode). |
| `n_answers_insufficient_context` | Answers in which the model declared the retrieved context insufficient instead of answering. |
| `retrieved_evidence_hit_rate`, `retrieved_evidence_mean_recall` | The same overlap metrics applied to the retrieved evidence (titles, section texts, matched sentences) instead of the answer: the retrieval leg measured on its own, independent of any model. |

## Per-question keys (`per_question`, in this order)

| Key | Meaning |
|---|---|
| `question_id` | The dataset's own id for the question (`null` when the file has none). |
| `grounding_mode` | The mode this record was run in (`abstracts_only` / `full_text_refinement`). |
| `question` | The question text as asked. |
| `reference_answers` | The dataset's expected answer items (synonyms for factoid, N items for list questions). |
| `generated_answer` | The agent's answer text. Empty when the pipeline errored. |
| `cited_pmids` | PubMed ids the answer cites; each is guaranteed to be among the fetched publications (hallucinated ids are dropped and reported in `answer_warnings`). |
| `answer_insufficient_context` | `true` when the model said the retrieved context does not answer the question. |
| `answer_warnings` | Pipeline warnings on the answer (low retrieval relevance, dropped citations, …). |
| `error` | `null`, or the exception that ended this question's pipeline. |
| `elapsed_s` | Seconds from question in to answer out (judge excluded). |
| `biological_relevance_check` | The pre-retrieval LLM gate (ADR-008): `is_biomedical_question` and the model's `reason`. `null` when the gate is off. A `false` verdict ends the pipeline with no retrieval. |
| `sentence_search` | The LitSense sentence search: `n_sentences_returned` (page size, max 100), `n_sentences_scored` (sentences the reranker scored; the rest are an unscored tail), `n_distinct_publications`, `best_relevance_score` / `worst_relevance_score` (reranker scores of the scored sentences). |
| `publication_selection` | How the hits became the publication list: `n_publications_selected` (≤ `max_articles`), `n_dropped_without_pmid` (uncitable records), `n_dropped_below_min_score`. |
| `publication_fetch` | Fetching the configured section per selected publication: `n_publications_fetched`, `n_fetch_failures` (unresolvable pmids, dropped), `n_with_section_text` (publications whose abstract was not empty). |
| `full_text_refinement` | The depth loop (only in `full_text_refinement` mode, else `null`): `answer_judged_sufficient` (the depth evaluator's verdict on the first answer), `missing_information` (what it said was missing), `refinement_applied` (whether full text was fetched and the answer re-synthesised), `n_publications_upgraded_to_full_text`. |
| `entities_in_cited_publications` | PubTator entities (text, type, id) found in the cited publications' retrieved sentences. |
| `answer_overlap` | Deterministic overlap of `generated_answer` with `reference_answers`: `hit`, `recall`, `matched_items`, `missed_items`. |
| `retrieved_evidence_overlap` | The same overlap applied to the retrieved evidence text instead of the answer. |
| `llm_judge` | The judge's verdict: `score` (correctness 0–5), `informativeness` (0–5), `clarity` (0–5), `matched_items` / `missed_items` (its reading of which reference items the answer covers), `rationale`. `null` when no judge ran; `{"error": …}` when the judge call failed. |
| `agent_tokens` | The agent's token usage for this question: `input`, `output`, `reasoning`, `cache_read` (input tokens served from the provider's prompt cache, included in `input`), `total`, `calls`. |
| `judge_tokens` | The judge call's own usage, same fields. |
| `previous_judges` | Only present after `litsense.rejudge` replaced the judge: the earlier verdicts, each as `{judge_model, llm_judge, judge_tokens}`, oldest first. The headline `llm_judge` is always the judge named in `run_info.judge_model`. |

## Run folder

| File | Meaning |
|---|---|
| `<dataset>.json` | One dataset block as above, written the moment the dataset finishes. |
| `manifest.json` | The run's configuration: same keys as `run_info` plus `label`, `grounding_modes`, `datasets`, `http_cache`, `pid`, `finished` (`null` while running or if interrupted), `files` (dataset files in run order). |
| `run.log` | Everything the run printed, flushed per line. |
| `REPORT.md` | The structured report rendered from the JSON files (tables only). |
| `pricing.json` | Present for matrix rows: the OpenRouter per-token prices (USD) of the model and the judge at the time the comparison was rendered, used for the cost columns. |

## Comparison (`results/matrix/`)

`COMPARISON.md` and `comparison.json` compare every run folder under
`results/matrix/runs/`. The JSON holds `runs` (label, model, reasoning, judge, timing,
datasets completed, total tokens, agent and judge cost in USD) and
`cells_by_dataset_mode_run[dataset][grounding_mode][run label]` = that run's aggregate
keys plus `mean_reasoning_tokens`, `cost_usd`, `judge_cost_usd`.
