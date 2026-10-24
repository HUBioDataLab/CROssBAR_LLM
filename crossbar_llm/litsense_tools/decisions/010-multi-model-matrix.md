# ADR-010 — Multi-model comparison: reasoning knob, shared response cache, parallel runs

**Status:** Accepted — 2026-09-22. Owner request: run the benchmark over a list of
OpenRouter models (some in a "with reasoning" and a "without reasoning" variant), in
parallel rather than one after another, and report the results side by side with the
JSON files.

## Context

The harness already produces one folder per run (`litsense/results/runs/<stamp>-
<label>/`) and the report per folder. Three things were missing for a matrix of 15
configurations over the five active sets:

1. **A way to ask a model to reason, or not.** Reasoning is a request parameter, not a
   model name: `gpt-5.4` and `gpt-5.4_reasoning_medium` are the same model id with a
   different `reasoning` object. Several models reason **by default** (glm-5.2, and
   gemini-3.5-flash cannot switch it off at all), so a "no reasoning" run has to say so
   explicitly or it silently reasons.
2. **A way to run fifteen processes against NCBI without fifteen-fold traffic.** The
   client's rate limit is per process (invariant 5 is "one shared limiter per run"), and
   NCBI is a guest service (ADR-002). Fifteen processes at 1 req/s each is not a guest.
   The retrieval leg, however, is identical for every model: the same 350 questions
   produce the same searches and the same publication fetches. Only which full texts
   get pulled varies (it depends on what the model cites), and even those overlap
   heavily.
3. **A fixed judge.** With one model per run, "judge = model under test" (the reference
   harness's way) would make every row of the comparison graded by a different grader.

## Decision

### Reasoning: `Settings.reasoning_effort`

`None` (default) sends nothing — the provider default. `"none"` sends OpenRouter's
universal off switch `{"reasoning": {"enabled": false}}`. `"minimal" | "low" | "medium"
| "high"` send `{"reasoning": {"effort": <level>}}`. The object travels as `extra_body`
on the OpenAI-compatible provider (which is how OpenRouter is reached); asking for a
level on any other provider raises instead of being ignored, because a "reasoning" run
that did not reason would poison the comparison. `llm.build_chat_model` is the single
place that applies it, so the gate, the synthesizer and the depth evaluator all reason
alike; the judge is built separately and never inherits it. Reasoning tokens land in
`TokenUsage.reasoning` (OpenRouter counts them inside output tokens and bills them as
output; the report shows them on their own as well).

Per-model facts from OpenRouter's `/api/v1/models` `reasoning` block (2026-09-22),
recorded in `benchmarks/models.json` next to the choice they forced:

| model | reasoning block | consequence for the matrix |
|---|---|---|
| gemini-3.5-flash | `mandatory: true`, default medium, efforts high/medium/low/minimal | cannot be switched off; the "no reasoning" row runs at `minimal` and is labelled so |
| glm-5.2 | `default_enabled: true`, efforts xhigh/high | the plain row sends `enabled: false` explicitly |
| deepseek-v4-flash / -pro | efforts xhigh/high only | the owner asked for `medium`; what the smoke test shows OpenRouter does with it is recorded in the run manifest and the notes |
| gpt-5.4 family | `default_enabled: false`, efforts incl. `none` | plain rows send `enabled: false`; reasoning rows `effort: medium` |
| claude-opus-4.8 / sonnet-4.6 | `default_enabled: false` | plain rows send `enabled: false` |
| claude-haiku-4.5 | no effort selection exposed | nothing sent |

### Shared on-disk response cache: `Settings.http_cache_dir` / `--http-cache`

`client.ResponseCache`: one JSON file per URL (status, content type, body), written
atomically, read before any request. Only **final** responses are stored — the ones the
client would never retry: 200s (including BioC-PMC's "no result" HTML page, ADR-009),
404s, and the 500 that means "publication not found" (ADR-005). A miss takes a lock file
(`O_EXCL`); other processes that miss the same URL poll for the file instead of fetching
too. A lock older than two minutes is treated as abandoned by a dead process and taken
over. Off by default (`None`): the library's behaviour is unchanged; the benchmark
opts in with `--http-cache`.

Consequences: every run in the matrix sees **identical retrieval** (no index-side
churn between rows, which is a fairness gain), and NCBI sees roughly one process's
worth of traffic however many run — the leader pays for each URL once, the rest read
it back. The first process to start warms the cache for everyone. It also means a
rerun replays retrieval from disk: delete `benchmarks/.http-cache/` to measure against
the live index again.

### One detached process per configuration: `litsense/scripts/run_model_matrix.py`

`launch` starts every entry of `benchmarks/models.json` as its own detached
`litsense.run` process (`--dataset all --mode both --judge --judge-model <fixed>
--http-cache --run-name <label> [--reasoning <level>]`), `status` reads progress from
each run folder, `stop` kills them, `pricing` writes OpenRouter's per-token prices into
each run folder, `compare` renders `litsense/results/COMPARISON.md` +
`comparison.json` (`litsense.report --compare`). The processes are independent: one
dying loses only its own run, and `--only` relaunches just that label.

### Fixed judge: `--judge-model`

The matrix judges every run with `openai:google/gemini-2.5-flash`, the model that judged
every earlier run, so the new rows compare with the 2026-09-15 baseline as well as with
each other. The judge's tokens stay separate from the agent's (as before).

## Alternatives rejected

- **Sequential runs.** Fifteen × ~2.5 h. The owner asked for parallel explicitly.
- **Lower per-process rate instead of a cache.** Fifteen processes at 1/15 req/s each
  would make every run fifteen times slower than one; the cache makes them faster than
  one (retrieval is read from disk for all but the leader).
- **A pre-warm dry run before launching.** Not needed: the leader of the matrix is the
  pre-warm for the others. Useful only if the matrix is ever launched on a cold cache
  with all rows being slow, expensive models.
- **LangChain's `reasoning_effort` kwarg.** OpenAI-only semantics; OpenRouter's unified
  `reasoning` object is what carries "off" and "effort" to every provider behind it.
