"""End-to-end benchmark harness for the PubTator3 agent.

Runs questions from BioASQ factoid / list and BioHopR through the full
LangGraph (router -> resolve -> partner_discovery? -> search -> export ->
synthesize -> evaluate_depth -> END) and scores the generated answers
against the reference data using deterministic token overlap plus an
optional LLM-as-judge pass.

Usage:
    poetry run python -m crossbar_llm.backend.tests.benchmark.run \
        --dataset bioasq-factoid --n 3 --judge --output bench.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

from crossbar_llm.backend.agents.pubtator3_graph import (
    _always_sufficient_evaluator,
    ainvoke_with_usage_capture,
    build_graph,
)
from crossbar_llm.backend.agents.paperclip_graph import (
    _always_sufficient_evaluator as _paperclip_always_sufficient_evaluator,
    build_graph as build_paperclip_graph,
)
from crossbar_llm.backend.tests.benchmark.metrics import (
    llm_judge,
    overlap_score,
)


BENCH_DIR = Path(__file__).parent

# Each dataset entry says where to find the JSON, which field holds the
# question, which holds the reference list, and whether the reference is
# "factoid" (one canonical term + synonyms — any match is a hit) or "list"
# (N items — recall is what we report).
DATASETS: dict[str, dict] = {
    "bioasq-factoid": {
        "path": BENCH_DIR / "BioASQ_10_selected_factoid_type_questions.json",
        "question_field": "body",
        "reference_field": "exact_answer",
        "kind": "factoid",
    },
    "bioasq-list": {
        "path": BENCH_DIR / "BioASQ_10_selected_list_type_questions.json",
        "question_field": "body",
        "reference_field": "exact_answer",
        "kind": "list",
    },
    "biohopr": {
        "path": BENCH_DIR / "BioHopR_selected_questions.json",
        "question_field": "hop2_question_multi",
        "reference_field": "answer",
        "kind": "list",
    },
    # CROssBAR knowledge-graph example queries. NO curated ground truth — the
    # reference lists were assembled from web search + domain knowledge (see
    # each item's `reference_note`) and are provisional. Most of these are
    # multi-hop / graph-traversal questions, which the router now routes to
    # out_of_scope, so expect the literature agent to DECLINE them; this
    # dataset mainly documents that boundary against the KG agent's domain.
    "crossbar": {
        "path": BENCH_DIR / "CROssBAR_example_queries.json",
        "question_field": "body",
        "reference_field": "exact_answer",
        "kind": "list",
    },
}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the PubTator3 agent against BioASQ / BioHopR benchmarks.",
    )

    # --dataset: which benchmark to evaluate against.
    #   bioasq-factoid: 10 short factual Qs. Reference is a single term
    #     (with synonyms as alternates). Hit = ANY synonym present in
    #     the answer.
    #   bioasq-list   : 10 list Qs. Reference is a flat list of items;
    #     we report how many of them the answer mentions (recall).
    #   biohopr       : 40 multi-hop graph-traversal Qs. Reference is a
    #     CROssBAR-KG truth set, not a PubMed list. Expect low scores —
    #     these are the KG agent's domain, not PubTator3's. The benchmark
    #     quantifies that gap rather than testing literature retrieval.
    #   all           : run all three sequentially.
    parser.add_argument(
        "--dataset",
        choices=list(DATASETS) + ["all"],
        default="bioasq-factoid",
        help="Which benchmark dataset to run.",
    )

    # --engine: which evidence tool to benchmark. Both consume the same
    # datasets and expose the same {final_answer, warnings, usage} contract, so
    # they are directly comparable.
    #   pubtator3 : entity/relation agent over the PubTator3 REST API (offline-
    #               mockable, free, no key).
    #   paperclip : full-text retrieval agent over the Paperclip MCP server.
    #               REQUIRES PAPERCLIP_API_KEY — it is a live, metered
    #               dependency and CANNOT run key-free.
    parser.add_argument(
        "--engine",
        choices=("pubtator3", "paperclip"),
        default="pubtator3",
        help="Which evidence tool to run (paperclip requires PAPERCLIP_API_KEY).",
    )

    # --n: sample size cap from the START of the dataset (deterministic
    # ordering). Use small values when iterating to control token budget;
    # leave unset to run the whole file.
    parser.add_argument(
        "--n",
        type=int,
        default=None,
        help="Sample size (first N questions per dataset). Omit for the full file.",
    )

    # --judge: ALSO run llm_judge() for each question, in addition to the
    # always-on overlap_score. Adds one extra LLM call per question (~2-3K
    # tokens). Off by default since token budget on free-tier providers
    # is the main constraint.
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Enable LLM-as-judge scoring in addition to token overlap.",
    )

    # --no-depth-eval: replace the depth-evaluator with the always-sufficient
    # no-op. Useful for benchmark runs because (a) refinement loops re-fetch
    # full text which balloons synth prompts to 50K+ tokens, and (b) the
    # benchmark is measuring the first-pass answer anyway.
    parser.add_argument(
        "--no-depth-eval",
        action="store_true",
        help="Skip the depth-evaluator node (disables the refinement loop).",
    )

    # --max-documents: passed straight through to build_graph(). Caps the
    # number of papers PubTator3 fetches per query. Default 4 keeps the
    # abstract-mode synth prompt under most provider per-request limits.
    parser.add_argument(
        "--max-documents",
        type=int,
        default=10,
        help="Max papers fetched per question (passed to build_graph).",
    )

    # --max-partners: passed straight through to build_graph(). Caps the
    # number of partners explored in relation_partner_discovery questions.
    # Each partner triggers one /search/ call, so this controls fanout.
    parser.add_argument(
        "--max-partners",
        type=int,
        default=3,
        help="Max partners explored for partner-discovery questions.",
    )

    # --pacing: seconds to sleep between questions. Necessary on rate-limited
    # providers — Groq free tier is 5 req/min and 100K tokens/day, Gemini
    # free tier is 5 req/min and 1.5M tokens/day. 3s lets the per-minute
    # window flush; bump higher if you hit RPM caps.
    parser.add_argument(
        "--pacing",
        type=float,
        default=3.0,
        help="Seconds to sleep between questions (rate-limit budget).",
    )

    # --output: dump per-question and aggregate metrics to a JSON file. The
    # console summary stays human-readable; the JSON is for downstream
    # analysis / charting.
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="If set, write detailed results to this JSON file.",
    )

    # --mode: which retrieval depth(s) to evaluate.
    #   abstracts : force abstracts-only (build_graph abstracts_only=True).
    #   full_text : let the router/evaluator decide (default behavior).
    #   both      : run each question twice — once in each mode — and emit
    #               a side-by-side comparison of quality and token cost.
    # `both` is the default because the whole point of the flag is the
    # comparison; flip to a single mode to halve the token budget.
    parser.add_argument(
        "--mode",
        choices=("abstracts", "full_text", "both"),
        default="both",
        help="Retrieval depth: abstracts-only, full-text-allowed, or both side-by-side.",
    )

    # --no-map: (Paperclip engine only) DISABLE Paperclip's `map`. Map is ON by
    # default (matching build_graph): it reads each paper's full text
    # SERVER-SIDE and extracts a per-paper answer used as the evidence body,
    # boosting recall on detail questions without pulling whole bodies through
    # our tokens (it costs Paperclip tokens + latency, ~5-10s/question). Pass
    # --no-map to synthesize from abstracts only (cheaper/faster). No effect on
    # the pubtator3 engine.
    parser.add_argument(
        "--no-map",
        action="store_true",
        help="(paperclip) Disable Paperclip's map; synthesize from abstracts only.",
    )

    # --filter: (Paperclip engine only) enable the server-side relevance trim
    # (build_graph(use_filter=...), OFF by default) between search and
    # assemble. Best-effort/REST-only — see docs/paperclip_tool.md §5.11.
    parser.add_argument(
        "--filter",
        action="store_true",
        help="(paperclip) Enable Paperclip's relevance filter before context assembly.",
    )

    return parser.parse_args()


# --------------------------------------------------------------------------- #
# Per-question runner
# --------------------------------------------------------------------------- #

async def _run_one(
    graph,
    judge_model,
    question: str,
    reference: list[str],
    kind: str,
    run_judge: bool,
) -> dict:
    """Run a single question through the graph and score it.

    Returns a per-question record with router decision, generated answer,
    elapsed time, and both scoring results (overlap always, judge optional).
    """
    t0 = time.perf_counter()
    state: dict = {}
    usage: dict = {}
    error: str | None = None
    try:
        state, usage = await ainvoke_with_usage_capture(
            graph, {"question": question, "warnings": []}
        )
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    elapsed = time.perf_counter() - t0
    generated = state.get("final_answer") or ""

    overlap = overlap_score(generated, reference, kind=kind)  # type: ignore[arg-type]

    judge_verdict: dict | None = None
    if run_judge and generated and judge_model is not None:
        try:
            verdict = await llm_judge(
                question, generated, reference, judge_model, kind=kind,  # type: ignore[arg-type]
            )
            judge_verdict = verdict.model_dump()
        except Exception as e:
            judge_verdict = {"error": f"{type(e).__name__}: {e}"}

    passages = state.get("passages") or []
    section_counts: dict[str, int] = {}
    for p in passages:
        section_counts[p.section] = section_counts.get(p.section, 0) + 1

    return {
        "question": question,
        "reference": reference,
        "generated": generated,
        "error": error,
        "elapsed_s": round(elapsed, 1),
        "router": {
            "question_type": state.get("question_type"),
            "rationale": state.get("rationale"),
            "mentions": [
                {"text": m.text, "type": m.suggested_type, "role": m.role}
                for m in (state.get("mentions") or [])
            ],
            "relation": state.get("relation"),
            "e2_type": state.get("e2_type"),
            "keyword_query": state.get("keyword_query"),
            "full_text": bool(state.get("full_text", False)),
            # Paperclip-engine routing fields (which corpus the query hit, etc.).
            "source": state.get("source"),
            "search_query": state.get("search_query"),
            "sections": state.get("sections"),
        },
        "resolve": {
            "resolved": {
                k: v.accession for k, v in (state.get("resolved") or {}).items()
            },
            "unresolved": state.get("unresolved", []),
        },
        "partner_discovery": {
            "n_partners": len(state.get("partners") or []),
            "top_partners": [
                {
                    "source": p.source,
                    "target": p.target,
                    "publications": p.publications,
                }
                for p in (state.get("partners") or [])[:5]
            ],
        },
        "search": {
            "queries_used": state.get("queries_used", []),
            "n_pmids": len(state.get("pmids") or []),
            "total_articles": state.get("total_articles", 0),
            # Paperclip-engine counters (empty for PubTator3 runs).
            "n_hits": len(state.get("hits") or []),
            "n_citations": len(state.get("citations") or []),
        },
        "export": {
            "n_documents": len(state.get("documents") or []),
            "n_passages": len(passages),
            "section_breakdown": dict(sorted(section_counts.items())),
            # Paperclip engine: how many assembled docs carry body evidence
            # (a map extraction or full-text), vs abstract-only.
            "n_with_body": sum(
                1 for d in (state.get("documents") or []) if getattr(d, "body", None)
            ),
        },
        "evaluate": {
            "depth_sufficient": state.get("depth_sufficient"),
            "depth_missing": state.get("depth_missing"),
            "depth_skip_reason": state.get("depth_skip_reason"),
            "refinement_attempted": bool(state.get("refinement_attempted")),
            # Mirror the post-evaluator state of the section filter so the
            # caller can see whether the evaluator narrowed/widened it.
            "sections_after": state.get("sections"),
            "full_text_after": bool(state.get("full_text")),
        },
        "router_extras": {
            "sections": state.get("sections")
            if not state.get("refinement_attempted")
            else None,
        },
        "warnings": state.get("warnings", []),
        "overlap": overlap,
        "judge": judge_verdict,
        "tokens": {
            "input": usage.get("input_tokens", 0),
            "output": usage.get("output_tokens", 0),
            "reasoning": usage.get("reasoning_tokens", 0),
            "cache_read": usage.get("cache_read_tokens", 0),
            "total": usage.get("total_tokens", 0),
        },
    }


def _print_question_detail(res: dict, reference: list[str]) -> None:
    router = res.get("router") or {}
    resolve = res.get("resolve") or {}
    partner = res.get("partner_discovery") or {}
    search = res.get("search") or {}
    export = res.get("export") or {}

    print("  [ROUTING]")
    print(f"    type          : {router.get('question_type')}")
    # Paperclip engine: which corpus the query was sent to (pmc / proteins / ...).
    if router.get("source"):
        src_line = f"    source        : {router['source']}"
        if router.get("sections"):
            src_line += f"  sections={router['sections']}"
        print(src_line)
    if router.get("rationale"):
        rationale = router["rationale"]
        if len(rationale) > 140:
            rationale = rationale[:140] + "..."
        print(f"    rationale     : {rationale!r}")
    if router.get("mentions"):
        mentions = router["mentions"]
        compact = [
            f"{m['text']}({m['type']}{','+m['role'] if m['role'] else ''})"
            for m in mentions
        ]
        print(f"    mentions      : [{', '.join(compact)}]")
    if router.get("relation"):
        print(f"    relation      : {router['relation']}")
    if router.get("e2_type"):
        print(f"    e2_type       : {router['e2_type']}")
    if router.get("keyword_query"):
        print(f"    keyword_query : {router['keyword_query']!r}")
    print(f"    full_text     : {router.get('full_text', False)}")

    resolved = resolve.get("resolved") or {}
    unresolved = resolve.get("unresolved") or []
    if resolved or unresolved:
        print("  [RESOLVE]")
        if resolved:
            pairs = ", ".join(f"{k!r}→{v}" for k, v in resolved.items())
            print(f"    resolved      : {pairs}")
        if unresolved:
            print(f"    unresolved    : {unresolved}")

    if partner.get("n_partners"):
        print("  [PARTNER_DISCOVERY]")
        top = partner.get("top_partners") or []
        for p in top:
            print(f"    - {p['source']} → {p['target']} (pubs={p['publications']})")
        if partner["n_partners"] > len(top):
            print(f"    ... and {partner['n_partners'] - len(top)} more")

    queries = search.get("queries_used") or []
    n_pmids = search.get("n_pmids") or 0
    total_articles = search.get("total_articles") or 0
    # Paperclip-engine counters (empty for PubTator3 runs, and vice versa).
    n_hits = search.get("n_hits") or 0
    n_citations = search.get("n_citations") or 0
    if queries or n_pmids or n_hits:
        print("  [SEARCH]")
        for q in queries[:3]:
            print(f"    query         : {q!r}")
        if len(queries) > 3:
            print(f"    ... and {len(queries) - 3} more queries")
        if n_pmids:
            # PubTator3 engine: distinct PMIDs from the structured/keyword search.
            print(f"    total_hits    : {total_articles}")
            print(f"    unique_pmids  : {n_pmids}")
        else:
            # Paperclip engine: ranked hits and the citable subset.
            print(f"    hits          : {n_hits}")
            print(f"    citable       : {n_citations}")

    n_docs = export.get("n_documents") or 0
    n_passages = export.get("n_passages") or 0
    sections = export.get("section_breakdown") or {}
    if n_docs:
        print("  [EXPORT]")
        print(f"    documents     : {n_docs}")
        if n_passages:
            # PubTator3 engine: passage/section breakdown.
            section_str = ", ".join(f"{s}:{c}" for s, c in sections.items())
            print(f"    passages      : {n_passages} ({section_str})")
        else:
            # Paperclip engine: abstracts vs. body (map/full-text) evidence.
            n_body = export.get("n_with_body") or 0
            print(f"    evidence      : {n_body} with body (map/full-text), "
                  f"{n_docs - n_body} abstract-only")

    if res["generated"]:
        print("  [SYNTHESIZE]")
        lines = res["generated"].splitlines()
        print(f"    answer ({len(res['generated'])} chars, {len(lines)} lines):")
        for line in lines[:12]:
            print(f"      {line}")
        if len(lines) > 12:
            print(f"      ... ({len(lines) - 12} more lines)")

    evaluate = res.get("evaluate") or {}
    sufficient = evaluate.get("depth_sufficient")
    skip_reason = evaluate.get("depth_skip_reason")
    refined = evaluate.get("refinement_attempted")
    print("  [EVALUATE]")
    if sufficient is None:
        # Node never executed (router-terminated path, no passages, etc.).
        if res.get("router", {}).get("question_type") == "out_of_scope":
            print("    verdict       : skipped (out_of_scope — router terminated)")
        else:
            print("    verdict       : skipped (evaluator node not reached)")
    elif skip_reason and skip_reason.startswith("evaluator error"):
        # LLM call failed; we accepted by default but the verdict is fake.
        print(f"    verdict       : ERROR — accepted by default")
        print(f"    reason        : {skip_reason}")
    elif skip_reason:
        # Short-circuited deterministically (abstracts_only, no escalation lever,
        # refinement already attempted) — no LLM call was made.
        print(f"    verdict       : skipped — {skip_reason}")
    else:
        # Real LLM verdict.
        verdict = "sufficient" if sufficient else "INSUFFICIENT"
        print(f"    verdict       : {verdict}")
        if evaluate.get("depth_missing"):
            print(f"    missing       : {evaluate['depth_missing']!r}")
        if refined:
            print(
                f"    refinement    : TRIGGERED — re-fetched with "
                f"full_text={evaluate.get('full_text_after')}, "
                f"sections={evaluate.get('sections_after')}"
            )
        else:
            print("    refinement    : not triggered")

    print("  [SCORING]")
    print(
        f"    overlap       : hit={res['overlap']['hit']}, "
        f"recall={res['overlap']['recall']:.2f}, "
        f"matched={len(res['overlap']['matched'])}/{len(reference)}"
    )
    if res["overlap"]["matched"]:
        print(f"    matched       : {res['overlap']['matched']}")
    if res["overlap"]["missed"]:
        missed = res["overlap"]["missed"]
        if len(missed) <= 5:
            print(f"    missed        : {missed}")
        else:
            print(f"    missed ({len(missed)}): {missed[:5]} ...")
    if res["judge"]:
        if "error" in res["judge"]:
            print(f"    judge         : error: {res['judge']['error']}")
        else:
            print(
                f"    judge         : score={res['judge']['score']}/5, "
                f"matched={len(res['judge']['matched_items'])}, "
                f"informativeness={res['judge'].get('informativeness', '?')}/5, "
                f"clarity={res['judge'].get('clarity', '?')}/5, "
                f"rationale={res['judge']['rationale']!r}"
            )

    tokens = res.get("tokens") or {}
    if tokens.get("total"):
        print("  [TOKENS]")
        print(
            f"    input={tokens.get('input', 0)}  "
            f"output={tokens.get('output', 0)}  "
            f"reasoning={tokens.get('reasoning', 0)}  "
            f"total={tokens.get('total', 0)}"
        )

    if res.get("elapsed_s") is not None:
        print("  [TIMING]")
        print(f"    response time : {res['elapsed_s']:.1f}s")

    if res.get("warnings"):
        print(f"  [WARNINGS] {res['warnings']}")


def _aggregate(results: list[dict]) -> dict:
    """Roll per-question results into headline numbers."""
    n = len(results) or 1
    n_completed = sum(1 for r in results if r["generated"] and not r["error"])
    hit_rate = sum(1 for r in results if r["overlap"]["hit"]) / n
    mean_recall = sum(r["overlap"]["recall"] for r in results) / n

    judge_scores = [
        r["judge"]["score"]
        for r in results
        if r.get("judge") and "score" in r["judge"]
    ]
    mean_judge = sum(judge_scores) / len(judge_scores) if judge_scores else None

    def _mean_judge_field(field: str) -> float | None:
        vals = [
            r["judge"][field]
            for r in results
            if r.get("judge") and field in r["judge"]
        ]
        return sum(vals) / len(vals) if vals else None

    mean_informativeness = _mean_judge_field("informativeness")
    mean_clarity = _mean_judge_field("clarity")

    total_tokens = sum((r.get("tokens") or {}).get("total", 0) for r in results)
    mean_tokens = total_tokens / n
    total_in = sum((r.get("tokens") or {}).get("input", 0) for r in results)
    total_out = sum((r.get("tokens") or {}).get("output", 0) for r in results)
    total_reasoning = sum((r.get("tokens") or {}).get("reasoning", 0) for r in results)

    elapsed = [r["elapsed_s"] for r in results if r.get("elapsed_s") is not None]
    total_elapsed_s = sum(elapsed)
    mean_elapsed_s = total_elapsed_s / len(elapsed) if elapsed else None
    max_elapsed_s = max(elapsed) if elapsed else None

    return {
        "n": len(results),
        "n_completed": n_completed,
        "hit_rate": round(hit_rate, 3),
        "mean_recall": round(mean_recall, 3),
        "mean_judge": round(mean_judge, 2) if mean_judge is not None else None,
        "mean_informativeness": round(mean_informativeness, 2) if mean_informativeness is not None else None,
        "mean_clarity": round(mean_clarity, 2) if mean_clarity is not None else None,
        "total_tokens": total_tokens,
        "mean_tokens": round(mean_tokens, 1),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_reasoning_tokens": total_reasoning,
        "mean_input_tokens": round(total_in / n, 1),
        "mean_output_tokens": round(total_out / n, 1),
        "total_elapsed_s": round(total_elapsed_s, 1),
        "mean_elapsed_s": round(mean_elapsed_s, 1) if mean_elapsed_s is not None else None,
        "max_elapsed_s": round(max_elapsed_s, 1) if max_elapsed_s is not None else None,
    }


def _print_comparison(name: str, agg_a: dict, agg_b: dict) -> None:
    """Side-by-side abstracts vs full_text aggregate table."""
    print(f"\n  --- {name} side-by-side (abstracts vs full_text) ---")
    rows = [
        ("completed",    f"{agg_a['n_completed']}/{agg_a['n']}", f"{agg_b['n_completed']}/{agg_b['n']}"),
        ("hit rate",     f"{agg_a['hit_rate']:.2f}",             f"{agg_b['hit_rate']:.2f}"),
        ("mean recall",  f"{agg_a['mean_recall']:.2f}",          f"{agg_b['mean_recall']:.2f}"),
    ]
    def _judge_row(label: str, key: str) -> None:
        if agg_a.get(key) is not None or agg_b.get(key) is not None:
            rows.append((
                label,
                f"{agg_a[key]:.2f}/5" if agg_a.get(key) is not None else "—",
                f"{agg_b[key]:.2f}/5" if agg_b.get(key) is not None else "—",
            ))

    _judge_row("mean judge", "mean_judge")
    _judge_row("mean informat.", "mean_informativeness")
    _judge_row("mean clarity", "mean_clarity")
    if agg_a.get("mean_elapsed_s") is not None or agg_b.get("mean_elapsed_s") is not None:
        rows.append((
            "mean resp time",
            f"{agg_a['mean_elapsed_s']:.1f}s" if agg_a.get("mean_elapsed_s") is not None else "—",
            f"{agg_b['mean_elapsed_s']:.1f}s" if agg_b.get("mean_elapsed_s") is not None else "—",
        ))
    rows.append(("total in tok",  f"{agg_a['total_input_tokens']:,}",  f"{agg_b['total_input_tokens']:,}"))
    rows.append(("total out tok", f"{agg_a['total_output_tokens']:,}", f"{agg_b['total_output_tokens']:,}"))
    rows.append(("total tokens",  f"{agg_a['total_tokens']:,}",        f"{agg_b['total_tokens']:,}"))
    rows.append(("in tok / Q",    f"{agg_a['mean_input_tokens']:,.0f}",  f"{agg_b['mean_input_tokens']:,.0f}"))
    rows.append(("out tok / Q",   f"{agg_a['mean_output_tokens']:,.0f}", f"{agg_b['mean_output_tokens']:,.0f}"))
    rows.append(("tokens / Q",    f"{agg_a['mean_tokens']:,.0f}",        f"{agg_b['mean_tokens']:,.0f}"))

    width = max(len(r[0]) for r in rows)
    print(f"  {'metric'.ljust(width)}  {'abstracts':>14}  {'full_text':>14}")
    print(f"  {'-' * width}  {'-' * 14}  {'-' * 14}")
    for label, a, b in rows:
        print(f"  {label.ljust(width)}  {a:>14}  {b:>14}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

async def _amain(args: argparse.Namespace) -> int:
    # The benchmark needs a configured chat model. We borrow the same
    # `get_llm()` helper the demos use — keeps a single source of truth
    # for provider / model selection. Live in tmp/ since it's also where
    # the demos live.
    repo_root = Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(repo_root / "tmp"))
    try:
        from _llm import get_llm  # type: ignore[import-not-found]
    except ImportError as e:
        print(f"ERROR: could not import tmp/_llm.py: {e}", file=sys.stderr)
        return 2
    llm = get_llm()

    # --no-depth-eval replaces the inline LLM-backed evaluator with a no-op
    # that always returns sufficient=True. The graph topology still includes
    # the evaluate_depth node — it just always routes to END. Each engine has
    # its own no-op (the state / verdict types differ).
    graph_kwargs: dict = {}
    if args.no_depth_eval:
        graph_kwargs["evaluator"] = (
            _paperclip_always_sufficient_evaluator
            if args.engine == "paperclip"
            else _always_sufficient_evaluator
        )

    def _make_graph(abstracts_only: bool):
        if args.engine == "paperclip":
            # Paperclip's build_graph has no `max_partners` (no relation routes);
            # the live MCP adapter is constructed internally from PAPERCLIP_API_KEY.
            return build_paperclip_graph(
                chat_model=llm,
                max_documents=args.max_documents,
                abstracts_only=abstracts_only,
                use_map=not args.no_map,
                use_filter=args.filter,
                **graph_kwargs,
            )
        return build_graph(
            chat_model=llm,
            max_partners=args.max_partners,
            max_documents=args.max_documents,
            abstracts_only=abstracts_only,
            **graph_kwargs,
        )

    # When --mode=both we need two graphs (one per abstracts_only setting),
    # each will receive every question. Otherwise a single graph runs.
    modes: list[str] = ["abstracts", "full_text"] if args.mode == "both" else [args.mode]
    graphs: dict[str, object] = {}
    for mode in modes:
        graphs[mode] = _make_graph(abstracts_only=(mode == "abstracts"))

    # The same chat model is reused for the LLM-judge call when --judge is on.
    # For accurate grading you'd want a stronger model, but to keep budget
    # symmetry with the rest of the run we just reuse `llm`.
    judge_model = llm if args.judge else None

    datasets = list(DATASETS) if args.dataset == "all" else [args.dataset]
    all_results: dict[str, dict] = {}

    for ds_name in datasets:
        ds = DATASETS[ds_name]
        items = json.loads(ds["path"].read_text())
        if args.n is not None:
            items = items[: args.n]

        header = f"=== {ds_name} ({len(items)} questions) ==="
        print(f"\n{'=' * len(header)}\n{header}\n{'=' * len(header)}")

        # per_mode_results[mode] = list[per-question dict]
        per_mode_results: dict[str, list[dict]] = {m: [] for m in modes}
        for i, item in enumerate(items, start=1):
            question = item[ds["question_field"]]
            reference = item[ds["reference_field"]]
            if isinstance(reference, str):
                reference = [reference]

            if i > 1:
                await asyncio.sleep(args.pacing)

            print(f"\n[{i}/{len(items)}] Q: {question}")

            if len(reference) <= 5:
                print(f"  expected ({len(reference)}): {reference}")
            else:
                print(f"  expected ({len(reference)}):")
                for ref_item in reference[:8]:
                    print(f"    - {ref_item}")
                if len(reference) > 8:
                    print(f"    ... and {len(reference) - 8} more")

            # Run the same question through each mode back-to-back. Pacing
            # between modes uses the same window as between questions.
            for j, mode in enumerate(modes):
                if j > 0:
                    await asyncio.sleep(args.pacing)
                print(f"\n  ── mode: {mode} ──")
                res = await _run_one(
                    graph=graphs[mode],
                    judge_model=judge_model,
                    question=question,
                    reference=reference,
                    kind=ds["kind"],
                    run_judge=args.judge,
                )
                res["mode"] = mode
                per_mode_results[mode].append(res)

                _print_question_detail(res, reference)

                if res["error"]:
                    print(f"  ERROR       : {res['error']}")

        # Aggregate + emit summary. With one mode it's the original block;
        # with two we print each aggregate AND a side-by-side table.
        per_mode_agg: dict[str, dict] = {}
        for mode in modes:
            per_mode_agg[mode] = _aggregate(per_mode_results[mode])

        all_results[ds_name] = {
            "modes": modes,
            "per_mode": {
                mode: {
                    **per_mode_agg[mode],
                    "per_question": per_mode_results[mode],
                }
                for mode in modes
            },
        }

        for mode in modes:
            agg = per_mode_agg[mode]
            print(f"\n  --- {ds_name} aggregate ({mode}) ---")
            print(f"  completed     : {agg['n_completed']}/{agg['n']}")
            print(f"  hit rate      : {agg['hit_rate']:.2f}")
            print(f"  mean recall   : {agg['mean_recall']:.2f}")
            if agg["mean_judge"] is not None:
                print(f"  mean judge    : {agg['mean_judge']:.2f}/5")
            if agg.get("mean_informativeness") is not None:
                print(f"  mean informat.: {agg['mean_informativeness']:.2f}/5")
            if agg.get("mean_clarity") is not None:
                print(f"  mean clarity  : {agg['mean_clarity']:.2f}/5")
            print(f"  input tokens  : {agg['total_input_tokens']:,}  (mean {agg['mean_input_tokens']:,.0f}/Q)")
            print(f"  output tokens : {agg['total_output_tokens']:,}  (mean {agg['mean_output_tokens']:,.0f}/Q)")
            print(f"  total tokens  : {agg['total_tokens']:,}  (mean {agg['mean_tokens']:,.0f}/Q)")
            if agg.get("mean_elapsed_s") is not None:
                print(
                    f"  response time : {agg['mean_elapsed_s']:.1f}s mean, "
                    f"{agg['max_elapsed_s']:.1f}s max  "
                    f"(total {agg['total_elapsed_s']:.1f}s)"
                )

        if len(modes) == 2:
            _print_comparison(ds_name, per_mode_agg["abstracts"], per_mode_agg["full_text"])

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(all_results, indent=2, default=str))
        print(f"\nWrote {args.output}")

    return 0


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
