# LitSense literature tool

Grounded question answering over the biomedical literature via **LitSense 2.0**
(NCBI's sentence-level semantic search). A question goes in; one consolidated,
PMID-cited paragraph comes out, built only from the abstracts (or, optionally, the PMC
full text) that were actually retrieved. Delivered 2026-10-02; the standalone history is
in `https://github.com/oguzpar/litsense-agent`.

```
relevance ⇒ search → select → fetch → synthesize → (depth ⇄ refine) → validate → END
    ↓ (not a biomedical question)                    ↓ (insufficient: one full-text pass)
   END                                              refine → synthesize
```

- `relevance`: an LLM check that the question is a coherent biomedical question;
  nonsense routes to END with zero HTTP (ADR-008).
- `search` / `select`: LitSense sentence search (reranked), hits grouped into
  publications, ranking that handles the reranker's unscored tail (ADR-001/006).
- `fetch`: the abstract of each selected publication (rate-limited, retried, cached).
- `synthesize`: structured LLM output — answer text + the PMIDs it used.
- `depth` / `refine` (off by default): an LLM judges the answer's depth; if
  insufficient, cited abstracts are swapped for capped BioC-PMC full text and the
  answer is synthesised once more (ADR-009).
- `validate`: every cited PMID is checked against the fetched set; hallucinated
  citations are dropped and reported, never shipped (ADR-003).

## Use

```python
from crossbar_llm.litsense_tools import LitSenseAgent, Settings

async with LitSenseAgent(Settings(model="openai:google/gemini-2.5-flash")) as agent:
    answer = await agent.answer("Which deiodinase is known to be present in liver?")
    answer.text, answer.citations, answer.entities, answer.insufficient_context, answer.warnings

state = await agent.run("...")   # the full pipeline state: hits, selection, fetched contexts
```

`Settings` is pydantic-settings; every field is overridable by `LITSENSE_<FIELD>`
environment variables. The model string is provider-agnostic (LangChain
`init_chat_model`): `openai:<model>` with `OPENAI_API_KEY` + `OPENAI_BASE_URL=
https://openrouter.ai/api/v1` runs through OpenRouter. Knobs that matter: `full_text`
(the depth loop), `max_articles`, `reasoning_effort` / `provider_order` (OpenRouter),
`answer_style` (`prose` | `bare`). The LLM arrives through the injectable `Synthesizer`
seam in `llm.py`; plugging in another model is one adapter function.

## Layout

| Path | What |
|---|---|
| `agent.py` | `LitSenseAgent` — graph assembly, client lifecycle, the public surface |
| `config.py` | `Settings` |
| `models.py` | pydantic contracts pinned to captured LitSense / BioC-PMC responses |
| `client.py` | httpx client: rate limiter, retry, in-memory + optional on-disk cache |
| `llm.py`, `prompts.py` | chat-model factory, seams, prompts |
| `graph/nodes.py`, `graph/state.py` | the nodes; `select` and `validate` are pure functions |
| `tests/` | unit tests over captured fixtures, no network |
| `decisions/` | ADR-001 … ADR-010 |

Tests (scoped config, like the other tool suites):

```bash
uv run pytest -c crossbar_llm/litsense_tools/tests/pytest.ini crossbar_llm/litsense_tools/tests
```

## Benchmarks

The evaluation harness lives in the benchmarks project as `benchmarks/litsense/`
(`run.py`, `metrics.py`, `report.py`, `rejudge.py`, the dataset registry and files, the
multi-model matrix launcher). It follows Ahmet Oğuzhan's structure (deterministic overlap
+ LLM judge, hit rate / recall / judge / informativeness / clarity, tokens); every key of
its result files is documented in `benchmarks/litsense/RESULTS-SCHEMA.md`. Raw outputs of
every run (all generated answers, citations, judge rationales) are published as a
release of the standalone repository.
