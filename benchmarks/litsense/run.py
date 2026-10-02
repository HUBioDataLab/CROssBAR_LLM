"""End-to-end benchmark harness for the LitSense agent.

Runs benchmark questions through `LitSenseAgent` and scores the results against each
question's reference list, following the structure of Ahmet Oğuzhan's PubTator3 harness
(`reference/run.py`): deterministic token overlap always, LLM-as-judge optionally, headline
hit rate / mean recall, judge informativeness/clarity means, token usage, and an
abstracts-vs-full-text side-by-side via `--mode both` (the Trello comparison task). The
results contract (per-question keys, per-mode aggregate, file layout) lives in
`litsense/report.py`, which also renders the structured Markdown report.

One deliberate departure: the answer and the retrieved evidence are scored SEPARATELY.
The synthesis role is not connected to a model yet, so `--dry-run` runs retrieval for real
(no model, no API key) and the evidence overlap — did the fetched abstracts/titles/matched
sentences contain the reference items? — measures the retrieval leg on its own. Answer
overlap, the judge, and every non-abstracts mode only mean anything with a real model.

Every invocation is one **run** and lands in its own folder,
`litsense/results/runs/<YYYYMMDD-HHMMSS>-<label>/`: one `<dataset>.json` per dataset
(written the moment that dataset finishes, so an interrupted run keeps what it had),
`run.log` (everything printed), `manifest.json` (model, arguments, timing) and the
structured `REPORT.md` rendered over the folder's JSON files. Runs never mix.

Usage:
    uv run python -m litsense.run --dataset bioasq-factoid-100 --dry-run
    uv run python -m litsense.run --dataset all --mode both --judge   # the five active sets
    uv run python -m litsense.run --dataset bioasq-list-100 --mode both --judge --run-name bare
    # one model of a multi-model comparison (fixed judge, shared NCBI cache, reasoning on):
    LITSENSE_MODEL=openai:openai/gpt-5.4 uv run python -m litsense.run --mode both --judge \
        --judge-model openai:google/gemini-2.5-flash --http-cache --reasoning medium \
        --run-name gpt-5.4_reasoning_medium
`litsense/scripts/run_model_matrix.py` launches one such process per model in parallel and
`litsense.report --compare` renders the cross-run comparison.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from litsense.metrics import (
    Judge,
    JudgeVerdict,
    Kind,
    judge_messages,
    overlap_score,
)
from litsense.report import (
    GROUNDING_MODE_KEYS,
    RUNS_DIR,
    SCHEMA_DOC,
    aggregate,
    write_run_report,
)
from crossbar_llm.litsense_tools import LitSenseAgent, Settings
from crossbar_llm.litsense_tools.client import LitSenseClient
from crossbar_llm.litsense_tools.graph.state import PipelineState
from crossbar_llm.litsense_tools.llm import (
    UsageCollector,
    build_dry_run_relevance_checker,
    build_dry_run_synthesizer,
)
from crossbar_llm.litsense_tools.models import TokenUsage

BENCH_DIR = Path(__file__).parent
DATA_DIR = BENCH_DIR / "data"

#: Placeholder satisfying the required `model` field on dry runs, where no model is consulted.
DRY_RUN_MODEL = "dry-run:not-connected"

#: Where `--http-cache` puts the shared NCBI response cache unless told otherwise.
DEFAULT_HTTP_CACHE = BENCH_DIR / ".http-cache"

# Each dataset entry says where to find the JSON, which field holds the question, which
# holds the reference list, and whether the reference is "factoid" (one canonical term +
# synonyms — any match is a hit) or "list" (N items — recall is what we report). Field
# names follow the reference harness so the team's files drop in unchanged.
#
# `active` marks the sets the team works with since 2026-09-15 (the five large ones):
# `--dataset all` runs exactly those. The smaller pilot sets stay registered and runnable
# by name but are out of the default report.
DATASETS: dict[str, dict[str, Any]] = {
    "crossbar": {
        "path": DATA_DIR / "CROssBAR_example_queries.json",
        "question_field": "body",
        "reference_field": "exact_answer",
        "kind": "list",
        # NO curated ground truth — reference lists are provisional (see each item's
        # `reference_note`). Mostly multi-hop KG questions: expect low literature recall;
        # this dataset mainly probes the boundary against the KG agent's domain.
    },
    "bioasq-factoid": {
        "path": DATA_DIR / "BioASQ_10_selected_factoid_type_questions.json",
        "question_field": "body",
        "reference_field": "exact_answer",
        "kind": "factoid",
    },
    "bioasq-list": {
        "path": DATA_DIR / "BioASQ_10_selected_list_type_questions.json",
        "question_field": "body",
        "reference_field": "exact_answer",
        "kind": "list",
    },
    "biohopr": {
        "path": DATA_DIR / "BioHopR_selected_questions.json",
        "question_field": "hop2_question_multi",
        "reference_field": "answer",
        "kind": "list",
    },
    # Larger sets delivered 2026-08-29 — run these only after the small sets look right
    # (staged plan). The *-100 files are bigger BioASQ subsets in the same shape; the
    # three relation-path files are BioHopR-shaped (50 questions each).
    "bioasq-factoid-100": {
        "path": DATA_DIR / "factoid_subset.json",
        "question_field": "body",
        "reference_field": "exact_answer",
        "kind": "factoid",
        "active": True,
    },
    "bioasq-list-100": {
        "path": DATA_DIR / "list_subset.json",
        "question_field": "body",
        "reference_field": "exact_answer",
        "kind": "list",
        "active": True,
    },
    "biohopr-disease-protein-drug": {
        "path": DATA_DIR / "disease_protein_drug.json",
        "question_field": "hop2_question_multi",
        "reference_field": "answer",
        "kind": "list",
        "active": True,
    },
    "biohopr-drug-protein-disease": {
        "path": DATA_DIR / "drug_protein_disease.json",
        "question_field": "hop2_question_multi",
        "reference_field": "answer",
        "kind": "list",
        "active": True,
    },
    "biohopr-protein-disease-drug": {
        "path": DATA_DIR / "protein_disease_drug.json",
        "question_field": "hop2_question_multi",
        "reference_field": "answer",
        "kind": "list",
        "active": True,
    },
}

# The team's "Selected Question For Testing" card (2026-10-02) holds the same five sets
# sampled with seeds 48 and 50 (the sets above are seed 49). They drop in under
# `data/seed48/` and `data/seed50/` with the same file names; `--dataset seed48` /
# `seed50` run the five of one seed. Registry names carry the seed suffix so run
# folders, reports and the comparison tell the seeds apart.
SEEDED_SOURCES = {
    "bioasq-factoid-100": "factoid_subset.json",
    "bioasq-list-100": "list_subset.json",
    "biohopr-disease-protein-drug": "disease_protein_drug.json",
    "biohopr-drug-protein-disease": "drug_protein_disease.json",
    "biohopr-protein-disease-drug": "protein_disease_drug.json",
}
EXTRA_SEEDS = (48, 50)
for _seed in EXTRA_SEEDS:
    for _base, _file in SEEDED_SOURCES.items():
        DATASETS[f"{_base}-seed{_seed}"] = {
            **{k: v for k, v in DATASETS[_base].items() if k not in ("path", "active")},
            "path": DATA_DIR / f"seed{_seed}" / _file,
            "seed": _seed,
        }

#: The sets `--dataset all` runs and the default report covers (team decision 2026-09-15).
ACTIVE_DATASETS = [name for name, ds in DATASETS.items() if ds.get("active")]

#: `--dataset seedNN` -> that seed's five sets.
DATASET_GROUPS: dict[str, list[str]] = {
    "all": ACTIVE_DATASETS,
    **{f"seed{s}": [n for n, ds in DATASETS.items() if ds.get("seed") == s]
       for s in EXTRA_SEEDS},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the LitSense agent against benchmark questions and score the results.",
    )
    parser.add_argument(
        "--dataset",
        choices=[*DATASETS, *DATASET_GROUPS],
        default="all",
        help="Which benchmark dataset to run; 'all' = the five active sets "
        f"({', '.join(ACTIVE_DATASETS)}); 'seed48' / 'seed50' = the same five sets "
        "sampled with that seed (files under data/seedNN/). Missing data files are "
        "skipped with a notice.",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=None,
        help="Sample size (first N questions per dataset, after --offset). Omit for the "
        "full file.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first N questions per dataset. With --n this runs a chunk "
        "[offset, offset+n) — the manual-resume seam for interrupted long runs; "
        "chunk outputs merge with litsense/scripts/merge_benchmark_chunks.py.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No model, no API key: retrieval runs for real, synthesis and the relevance "
        "gate are pass-through stubs. Only the evidence metrics are meaningful.",
    )
    parser.add_argument(
        "--mode",
        choices=("abstracts", "full_text", "both"),
        default="abstracts",
        help="Ground answers on abstracts only, allow the ADR-009 full-text depth loop, or "
        "run every question in both modes for a side-by-side comparison. Non-abstracts "
        "modes need a live model (the depth evaluator is an LLM).",
    )
    parser.add_argument(
        "--answer-style",
        choices=("prose", "bare"),
        default="prose",
        help="'bare' asks the model for only the requested items (Trello evaluation card): "
        "sharper overlap scoring, no prose.",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Also run LLM-as-judge on each generated answer (one extra model call per "
        "question). Incompatible with --dry-run.",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        help="Override Settings.max_articles for the run.",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Provider-qualified model string for the LLM judge. Default: the model under "
        "test (the reference harness's way). Fix it across runs for a multi-model "
        "comparison, e.g. openai:google/gemini-2.5-flash.",
    )
    parser.add_argument(
        "--reasoning",
        choices=("none", "minimal", "low", "medium", "high"),
        default=None,
        help="Reasoning effort requested from the model under test (Settings."
        "reasoning_effort, ADR-010). Omit for the provider default; 'none' switches "
        "reasoning off explicitly. The judge never reasons beyond its own default.",
    )
    parser.add_argument(
        "--provider-order",
        default=None,
        help="OpenRouter only: comma-separated upstream providers to prefer for the model "
        "under test (Settings.provider_order), e.g. Alibaba,DeepInfra for DeepSeek V4.",
    )
    parser.add_argument(
        "--structured-output",
        choices=("json_schema", "function_calling", "json_mode"),
        default=None,
        help="How the model under test is asked for structured output (Settings."
        "structured_output_method). Omit for LangChain's default; 'function_calling' for "
        "models that ignore the JSON-schema response format (DeepSeek V4 via OpenRouter).",
    )
    parser.add_argument(
        "--http-cache",
        nargs="?",
        const=str(DEFAULT_HTTP_CACHE),
        default=None,
        metavar="DIR",
        help="Serve NCBI responses from an on-disk cache shared across processes "
        f"(ADR-010); default DIR {DEFAULT_HTTP_CACHE}. Parallel model runs over the same "
        "questions then make one request per URL between them.",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Label for the run folder (results/runs/<stamp>-<label>/). Default: the "
        "model's short name, or 'dry-run'.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=RUNS_DIR,
        help="Where the run folder is created (default results/runs/). The multi-model "
        "matrix launcher points every row at the matrix folder so runs and comparison "
        "land together.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional: additionally write all datasets of this run into one combined JSON "
        "file (the run folder is always written).",
    )
    return parser.parse_args()


def evidence_text(state: PipelineState | None) -> str:
    """Everything retrieval put on the table, as one scorable string.

    Titles, section texts and matched sentences of every fetched article — the text a
    connected model would ground on. Scoring this against the reference measures the
    retrieval leg independently of any model.
    """
    if state is None:
        return ""
    parts: list[str] = []
    for article in state.articles:
        if article.title:
            parts.append(article.title)
        if article.text:
            parts.append(article.text)
        parts.extend(article.matched_sentences)
    return "\n".join(parts)


async def run_one(
    agent: LitSenseAgent,
    question: str,
    reference: list[str],
    kind: Kind,
    judge: Judge | None,
    *,
    question_id: str | int | None = None,
    mode: str = "abstracts",
) -> dict[str, Any]:
    """Run one question through the agent and score it. Never raises.

    The record's keys are the results contract (`report.QUESTION_KEYS`, documented in
    `RESULTS-SCHEMA.md`); `mode` is the harness mode name and is written as its
    grounding-mode key.
    """
    t0 = time.perf_counter()
    state: PipelineState | None = None
    error: str | None = None
    try:
        state = await agent.run(question)
    except Exception as e:  # noqa: BLE001 — a failed question must not sink the run
        error = f"{type(e).__name__}: {e}"
    elapsed = time.perf_counter() - t0

    answer = state.answer if state is not None else None
    generated = answer.text if answer is not None else ""

    answer_overlap = overlap_score(generated, reference, kind=kind)
    evidence_overlap = overlap_score(evidence_text(state), reference, kind=kind)

    judge_verdict: dict[str, Any] | None = None
    judge_usage = TokenUsage()
    if judge is not None and generated:
        try:
            verdict, judge_usage = await judge(
                judge_messages(question, generated, reference, kind=kind)
            )
            judge_verdict = verdict.model_dump()
        except Exception as e:  # noqa: BLE001 — grading failure is a recorded result
            judge_verdict = {"error": f"{type(e).__name__}: {e}"}

    scored = (
        [hit for hit in state.hits if not hit.is_unscored] if state is not None else []
    )
    return {
        "question_id": question_id,
        "grounding_mode": GROUNDING_MODE_KEYS.get(mode, mode),
        "question": question,
        "reference_answers": reference,
        "generated_answer": generated,
        "cited_pmids": answer.citations if answer is not None else [],
        "answer_insufficient_context": (
            answer.insufficient_context if answer is not None else None
        ),
        "answer_warnings": answer.warnings if answer is not None else [],
        "error": error,
        "elapsed_s": round(elapsed, 1),
        "biological_relevance_check": (
            None
            if state is None or state.relevance is None
            else {
                "is_biomedical_question": state.relevance.relevant,
                "reason": state.relevance.reason,
            }
        ),
        "sentence_search": {
            "n_sentences_returned": len(state.hits) if state is not None else 0,
            "n_sentences_scored": len(scored),
            "n_distinct_publications": (
                len({h.pmid for h in state.hits if h.pmid is not None})
                if state is not None
                else 0
            ),
            "best_relevance_score": round(max((h.score for h in scored), default=0.0), 3),
            "worst_relevance_score": round(min((h.score for h in scored), default=0.0), 3),
        },
        "publication_selection": (
            None
            if state is None or state.selection is None
            else {
                "n_publications_selected": len(state.selection.articles),
                "n_dropped_without_pmid": state.selection.dropped_no_pmid,
                "n_dropped_below_min_score": state.selection.dropped_below_min_score,
            }
        ),
        "publication_fetch": {
            "n_publications_fetched": len(state.articles) if state is not None else 0,
            "n_fetch_failures": len(state.failed_pmids) if state is not None else 0,
            "n_with_section_text": (
                sum(1 for a in state.articles if a.has_text) if state is not None else 0
            ),
        },
        "full_text_refinement": (
            None
            if state is None or state.depth is None
            else {
                "answer_judged_sufficient": state.depth.sufficient,
                "missing_information": state.depth.missing,
                "refinement_applied": state.refined,
                "n_publications_upgraded_to_full_text": sum(
                    1 for a in state.articles if a.section == "full_text"
                ),
            }
        ),
        "entities_in_cited_publications": (
            [e.model_dump() for e in answer.entities] if answer is not None else []
        ),
        "answer_overlap": answer_overlap.model_dump(),
        "retrieved_evidence_overlap": evidence_overlap.model_dump(),
        "llm_judge": judge_verdict,
        "agent_tokens": (state.usage if state is not None else TokenUsage()).model_dump(),
        "judge_tokens": judge_usage.model_dump(),
    }


def _print_question_detail(res: dict[str, Any]) -> None:
    gate = res.get("biological_relevance_check")
    if gate is not None and not gate["is_biomedical_question"]:
        print(f"  [GATE] REJECTED: {gate['reason']!r}")
        return
    search, fetch = res["sentence_search"], res["publication_fetch"]
    print(
        f"  [SEARCH]   {search['n_sentences_returned']} hits, "
        f"{search['n_distinct_publications']} pmids, "
        f"scores {search['best_relevance_score']:.3f}..{search['worst_relevance_score']:.3f}"
    )
    print(
        f"  [FETCH]    {fetch['n_publications_fetched']} fetched "
        f"({fetch['n_with_section_text']} with text), {fetch['n_fetch_failures']} failed"
    )
    depth = res.get("full_text_refinement")
    if depth is not None:
        verdict = "sufficient" if depth["answer_judged_sufficient"] else "INSUFFICIENT"
        line = f"  [DEPTH]    {verdict}"
        if depth["refinement_applied"]:
            line += (f" — refined, {depth['n_publications_upgraded_to_full_text']} "
                     "article(s) upgraded to full text")
        elif not depth["answer_judged_sufficient"]:
            line += f" — missing: {depth['missing_information']!r}"
        print(line)
    for scope, overlap in (
        ("evidence", res["retrieved_evidence_overlap"]), ("answer", res["answer_overlap"])
    ):
        line = (
            f"  [{scope.upper():<8}] hit={overlap['hit']}, recall={overlap['recall']:.2f}, "
            f"matched {len(overlap['matched_items'])}/{len(res['reference_answers'])}"
        )
        if overlap["matched_items"]:
            line += f": {overlap['matched_items']}"
        print(line)
    judge = res.get("llm_judge")
    if judge is not None:
        if "error" in judge:
            print(f"  [JUDGE]    error: {judge['error']}")
        else:
            print(
                f"  [JUDGE]    score={judge['score']}/5, "
                f"informativeness={judge['informativeness']}/5, "
                f"clarity={judge['clarity']}/5 — {judge['rationale']!r}"
            )
    if res["answer_warnings"]:
        print(f"  [WARNINGS] {res['answer_warnings']}")
    if res["error"]:
        print(f"  [ERROR]    {res['error']}")
    tokens = res.get("agent_tokens") or {}
    if tokens.get("calls"):
        judge_tokens = res.get("judge_tokens") or {}
        print(
            f"  [TOKENS]   agent: input={tokens['input']}  output={tokens['output']}  "
            f"reasoning={tokens['reasoning']}  total={tokens['total']}  "
            f"({tokens['calls']} calls); judge: total={judge_tokens.get('total', 0)}"
        )
    print(f"  [TIMING]   {res['elapsed_s']:.1f}s")


def _print_aggregate(name: str, mode: str, agg: dict[str, Any]) -> None:
    print(f"\n--- {name} aggregate ({mode}) ---")
    print(f"  answered             : {agg['n_questions_answered']}/{agg['n_questions']}")
    print(f"  not biomedical (gate): {agg['n_rejected_not_biomedical']}")
    if agg["n_refined_with_full_text"]:
        print(f"  refined w/ full text : {agg['n_refined_with_full_text']}")
    print(f"  insufficient context : {agg['n_answers_insufficient_context']}")
    print(f"  evidence hit rate    : {agg['retrieved_evidence_hit_rate']:.2f}")
    print(f"  evidence mean recall : {agg['retrieved_evidence_mean_recall']:.2f}")
    print(f"  hit rate             : {agg['hit_rate']:.2f}")
    print(f"  mean recall          : {agg['mean_recall']:.2f}")
    if agg["mean_judge"] is not None:
        print(f"  mean judge           : {agg['mean_judge']:.2f}/5")
        print(f"  mean informativeness : {agg['mean_informativeness']:.2f}/5")
        print(f"  mean clarity         : {agg['mean_clarity']:.2f}/5")
    if agg["total_tokens"]:
        print(
            f"  input tokens         : {agg['total_input_tokens']:,}  "
            f"(mean {agg['mean_input_tokens']:,.0f}/Q)"
        )
        print(
            f"  output tokens        : {agg['total_output_tokens']:,}  "
            f"(mean {agg['mean_output_tokens']:,.0f}/Q)"
        )
        print(
            f"  total tokens         : {agg['total_tokens']:,}  "
            f"(mean {agg['mean_tokens']:,.0f}/Q)"
        )
        print(
            f"  judge tokens         : {agg['total_judge_tokens']:,}  "
            f"(mean {agg['mean_judge_tokens']:,.0f}/Q, not in the totals above)"
        )
    print(
        f"  response time        : {agg['mean_elapsed_s']:.1f}s mean, "
        f"{agg['max_elapsed_s']:.1f}s max  (total {agg['total_elapsed_s']:.1f}s)"
    )


def _print_comparison(name: str, a: dict[str, Any], b: dict[str, Any]) -> None:
    """Side-by-side abstracts vs full_text table (the Trello comparison task)."""

    def fmt5(value: float | None) -> str:
        return f"{value:.2f}/5" if value is not None else "—"

    rows = [
        ("answered", f"{a['n_questions_answered']}/{a['n_questions']}",
         f"{b['n_questions_answered']}/{b['n_questions']}"),
        ("refined w/ full text", str(a["n_refined_with_full_text"]),
         str(b["n_refined_with_full_text"])),
        ("hit rate", f"{a['hit_rate']:.2f}", f"{b['hit_rate']:.2f}"),
        ("mean recall", f"{a['mean_recall']:.2f}", f"{b['mean_recall']:.2f}"),
        ("mean judge", fmt5(a["mean_judge"]), fmt5(b["mean_judge"])),
        ("mean informat.", fmt5(a["mean_informativeness"]), fmt5(b["mean_informativeness"])),
        ("mean clarity", fmt5(a["mean_clarity"]), fmt5(b["mean_clarity"])),
        ("mean resp time", f"{a['mean_elapsed_s']:.1f}s", f"{b['mean_elapsed_s']:.1f}s"),
    ]
    if a["total_tokens"] or b["total_tokens"]:
        rows += [
            ("total in tok", f"{a['total_input_tokens']:,}", f"{b['total_input_tokens']:,}"),
            ("total out tok", f"{a['total_output_tokens']:,}", f"{b['total_output_tokens']:,}"),
            ("total tokens", f"{a['total_tokens']:,}", f"{b['total_tokens']:,}"),
            ("in tok / Q", f"{a['mean_input_tokens']:,.0f}", f"{b['mean_input_tokens']:,.0f}"),
            ("out tok / Q", f"{a['mean_output_tokens']:,.0f}", f"{b['mean_output_tokens']:,.0f}"),
            ("tokens / Q", f"{a['mean_tokens']:,.0f}", f"{b['mean_tokens']:,.0f}"),
        ]
    width = max(len(r[0]) for r in rows)
    print(f"\n  --- {name} side-by-side (abstracts vs full_text) ---")
    print(f"  {'metric'.ljust(width)}  {'abstracts':>12}  {'full_text':>12}")
    for label, left, right in rows:
        print(f"  {label.ljust(width)}  {left:>12}  {right:>12}")


def run_meta(args: argparse.Namespace, settings: Settings, *, started: str) -> dict[str, Any]:
    """What produced a results block — recorded so the report can say which model ran."""
    return {
        "harness": "litsense-agent",
        "model": "dry-run" if args.dry_run else settings.model,
        "reasoning_effort": settings.reasoning_effort,
        "structured_output_method": settings.structured_output_method,
        "provider_order": settings.provider_order,
        "judge_model": judge_model_string(args, settings),
        "answer_style": settings.answer_style,
        "max_articles": settings.max_articles,
        "question_offset": args.offset,
        "question_limit": args.n,
        "started": started,
        "schema": SCHEMA_DOC,
    }


def judge_model_string(args: argparse.Namespace, settings: Settings) -> str | None:
    """Which model judges: `--judge-model` when given, else the model under test."""
    if not args.judge:
        return None
    return str(args.judge_model or settings.model)


def build_judge(model_string: str, *, method: str | None = None) -> Judge:
    """A structured-output judge callable for the configured model.

    Same pattern as `crossbar_llm.litsense_tools.llm`: the provider package resolves from the model
    string at this point, not before. `method` overrides LangChain's structured-output
    method (`json_schema` / `function_calling` / `json_mode`) for judges served by
    providers that ignore the JSON-schema response format.
    """
    from langchain.chat_models import init_chat_model

    from crossbar_llm.litsense_tools.llm import load_provider_env

    load_provider_env()
    kwargs: dict[str, Any] = {"method": method} if method else {}
    structured = init_chat_model(model_string).with_structured_output(JudgeVerdict, **kwargs)

    async def judge(messages: list[tuple[str, str]]) -> tuple[JudgeVerdict, TokenUsage]:
        usage = UsageCollector()
        output = await structured.ainvoke(list(messages), config={"callbacks": [usage]})
        return JudgeVerdict.model_validate(output), usage.usage

    return judge


def model_label(model_string: str) -> str:
    """`openai:google/gemini-2.5-flash` → `gemini-2.5-flash`: a folder-safe run label."""
    tail = model_string.split(":", 1)[-1].rsplit("/", 1)[-1]
    return "".join(c if c.isalnum() or c in "._-" else "-" for c in tail) or "model"


def new_run_dir(label: str, *, root: Path = RUNS_DIR) -> Path:
    """Create `<root>/<YYYYMMDD-HHMMSS>-<label>/` — one folder per run, never reused."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = root / f"{stamp}-{label}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


class _Tee:
    """Duplicate console output into the run folder's `run.log`."""

    def __init__(self, console: TextIO, log_path: Path) -> None:
        self.console = console
        self.log = log_path.open("a", encoding="utf-8")

    def write(self, text: str) -> int:
        self.console.write(text)
        self.log.write(text)
        self.log.flush()  # the log is read live (tail -f) while the run is in flight
        return len(text)

    def flush(self) -> None:
        self.console.flush()
        self.log.flush()

    def close(self) -> None:
        self.log.close()


async def amain(args: argparse.Namespace) -> int:
    if args.judge and args.dry_run:
        print("--judge grades the generated answer; with --dry-run there is none. Pick one.")
        return 2
    if args.dry_run and args.mode != "abstracts":
        print("--mode full_text/both needs a live model (the depth evaluator is an LLM).")
        return 2

    overrides: dict[str, Any] = {"answer_style": args.answer_style}
    if args.max_articles is not None:
        overrides["max_articles"] = args.max_articles
    if args.reasoning is not None:
        overrides["reasoning_effort"] = args.reasoning
    if args.structured_output is not None:
        overrides["structured_output_method"] = args.structured_output
    if args.provider_order is not None:
        overrides["provider_order"] = args.provider_order
    if args.http_cache is not None:
        overrides["http_cache_dir"] = args.http_cache
    if args.dry_run:
        overrides["model"] = DRY_RUN_MODEL

    modes = ["abstracts", "full_text"] if args.mode == "both" else [args.mode]
    base_settings = Settings(**overrides)
    judge_model = judge_model_string(args, base_settings)
    judge = build_judge(judge_model) if judge_model else None

    label = args.run_name or ("dry-run" if args.dry_run else model_label(base_settings.model))
    run_dir = new_run_dir(label, root=args.runs_dir)
    tee = _Tee(sys.stdout, run_dir / "run.log")
    sys.stdout = tee  # a TextIO-shaped duplicate of the console
    names = DATASET_GROUPS.get(args.dataset, [args.dataset])
    manifest: dict[str, Any] = {
        "harness": "litsense-agent",
        "label": label,
        "model": "dry-run" if args.dry_run else base_settings.model,
        "reasoning_effort": base_settings.reasoning_effort,
        "structured_output_method": base_settings.structured_output_method,
        "provider_order": base_settings.provider_order,
        "judge_model": judge_model,
        "grounding_modes": [GROUNDING_MODE_KEYS[m] for m in modes],
        "answer_style": args.answer_style,
        "max_articles": base_settings.max_articles,
        "http_cache": base_settings.http_cache_dir,
        "pid": os.getpid(),
        "question_offset": args.offset,
        "question_limit": args.n,
        "datasets": names,
        "started": datetime.now().isoformat(timespec="seconds"),
        "finished": None,
        "files": [],
        "schema": SCHEMA_DOC,
    }
    _write_json(run_dir / "manifest.json", manifest)
    print(f"run folder: {run_dir}")
    seams: dict[str, Any] = (
        {
            "synthesizer": build_dry_run_synthesizer(),
            "relevance_checker": build_dry_run_relevance_checker(),
        }
        if args.dry_run
        else {}
    )

    # One shared client for every agent and mode: NCBI's rate limit belongs to the whole
    # run, and the per-pmid/per-pmcid caches make the second mode of --mode both cheap.
    client = LitSenseClient(base_settings)
    agents = {
        mode: LitSenseAgent(
            Settings(**{**overrides, "full_text": mode == "full_text"}),
            client=client,
            **seams,
        )
        for mode in modes
    }

    all_results: dict[str, Any] = {}
    try:
        for name in names:
            ds = DATASETS[name]
            if not ds["path"].exists():
                print(f"\n=== {name}: SKIPPED — {ds['path']} not present (see data/) ===")
                continue
            items = json.loads(ds["path"].read_text(encoding="utf-8"))
            if args.offset:
                items = items[args.offset :]
            if args.n is not None:
                items = items[: args.n]

            started = datetime.now().isoformat(timespec="seconds")
            run_label = "dry-run" if args.dry_run else base_settings.model
            if base_settings.reasoning_effort:
                run_label += f" [reasoning={base_settings.reasoning_effort}]"
            chunk = f", offset={args.offset}" if args.offset else ""
            print(f"\n=== {name} ({len(items)} questions{chunk}, {run_label}, "
                  f"style={args.answer_style}) ===")

            per_mode: dict[str, list[dict[str, Any]]] = {mode: [] for mode in modes}
            for i, item in enumerate(items, start=1):
                question = item[ds["question_field"]]
                reference = item[ds["reference_field"]]
                if isinstance(reference, str):
                    reference = [reference]
                print(f"\n[{i}/{len(items)}] Q: {question}")
                for mode in modes:
                    if len(modes) > 1:
                        print(f"  -- mode: {mode} --")
                    res = await run_one(
                        agents[mode], question, reference, ds["kind"], judge,
                        question_id=item.get("id"), mode=mode,
                    )
                    per_mode[mode].append(res)
                    _print_question_detail(res)

            aggregates = {mode: aggregate(per_mode[mode]) for mode in modes}
            all_results[name] = {
                "run_info": run_meta(args, base_settings, started=started),
                "grounding_modes": [GROUNDING_MODE_KEYS[m] for m in modes],
                "results_by_grounding_mode": {
                    GROUNDING_MODE_KEYS[mode]: {
                        **aggregates[mode], "per_question": per_mode[mode]
                    }
                    for mode in modes
                },
            }
            for mode in modes:
                _print_aggregate(name, mode, aggregates[mode])
            if len(modes) == 2:
                _print_comparison(name, aggregates["abstracts"], aggregates["full_text"])
            # Persist each dataset the moment it completes: a killed run keeps its
            # finished datasets, and the folder is self-describing at every point.
            _write_json(run_dir / f"{name}.json", {name: all_results[name]})
            manifest["files"].append(f"{name}.json")
            _write_json(run_dir / "manifest.json", manifest)
            print(f"\nWrote {run_dir / (name + '.json')}")
    finally:
        if client.cache is not None:
            print(
                f"\nhttp cache: {client.cache.hits} hits, {client.cache.misses} misses "
                f"({client.cache.directory})"
            )
        await client.aclose()
        manifest["finished"] = datetime.now().isoformat(timespec="seconds")
        _write_json(run_dir / "manifest.json", manifest)
        if manifest["files"]:
            print(f"Wrote {write_run_report(run_dir)}")
        sys.stdout = tee.console
        tee.close()

    if args.output is not None:
        _write_json(args.output, all_results)
        print(f"Wrote {args.output}")
    return 0


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    # Windows consoles can default to a legacy codepage that cannot encode characters
    # appearing in biomedical terms (e.g. the kappa in NF-κB); progress printing must
    # never kill a paid run over that. The JSON output file is written as UTF-8 either
    # way, so no data is lost — only the console rendering degrades.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    raise SystemExit(asyncio.run(amain(parse_args())))


if __name__ == "__main__":
    main()
