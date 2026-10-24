"""The results contract: aggregation, shape lifting and the structured report.

Pure JSON-in/JSON-out, so the tests pin exact numbers on synthetic records, the key
vocabulary against the reference harness's real output (`litsense/reference/
paperclip_long.sample.json`, Ahmet Oğuzhan's file trimmed to one question per dataset)
and the lifting of every layout this harness ever wrote.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from litsense.report import (
    QUESTION_KEYS,
    REFERENCE_KEY_MAP,
    aggregate,
    normalize_question,
    normalize_results,
    render_markdown,
    write_run_report,
)

SAMPLE = Path(__file__).parent.parent / "reference" / "paperclip_long.sample.json"


def record(
    *,
    hit: bool = True,
    recall: float = 1.0,
    judge: tuple[int, int, int] | None = (5, 4, 5),
    tokens: int = 100,
    elapsed: float = 10.0,
    error: str | None = None,
    refined: bool = False,
    insufficient: bool = False,
    gate_rejected: bool = False,
) -> dict[str, Any]:
    """A per-question record in the current key set."""
    return {
        "question_id": "q1",
        "grounding_mode": "abstracts_only",
        "question": "Which gene?",
        "reference_answers": ["TP53"],
        "generated_answer": "" if error else "TP53 is the answer.",
        "cited_pmids": [1],
        "answer_insufficient_context": insufficient,
        "answer_warnings": [],
        "error": error,
        "elapsed_s": elapsed,
        "biological_relevance_check": {"is_biomedical_question": not gate_rejected, "reason": ""},
        "sentence_search": {
            "n_sentences_returned": 100, "n_sentences_scored": 93, "n_distinct_publications": 90,
            "best_relevance_score": 0.8, "worst_relevance_score": 0.6,
        },
        "publication_selection": {
            "n_publications_selected": 10, "n_dropped_without_pmid": 0,
            "n_dropped_below_min_score": 0,
        },
        "publication_fetch": {
            "n_publications_fetched": 10, "n_fetch_failures": 0, "n_with_section_text": 10,
        },
        "full_text_refinement": {
            "answer_judged_sufficient": not refined, "missing_information": "",
            "refinement_applied": refined, "n_publications_upgraded_to_full_text": 0,
        },
        "entities_in_cited_publications": [],
        "answer_overlap": {"hit": hit, "recall": recall, "matched_items": [], "missed_items": []},
        "retrieved_evidence_overlap": {
            "hit": True, "recall": 1.0, "matched_items": ["TP53"], "missed_items": []
        },
        "llm_judge": None
        if judge is None
        else {
            "score": judge[0],
            "informativeness": judge[1],
            "clarity": judge[2],
            "matched_items": [],
            "missed_items": [],
            "rationale": "r",
        },
        "agent_tokens": {
            "input": tokens - 20, "output": 15, "reasoning": 5, "cache_read": 0,
            "total": tokens, "calls": 2,
        },
        "judge_tokens": {
            "input": 40, "output": 10, "reasoning": 0, "cache_read": 0, "total": 50, "calls": 1
        },
    }


# --- aggregate ---------------------------------------------------------------------------


def test_every_reference_harness_key_maps_to_one_of_ours() -> None:
    agg = aggregate([record()])
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    his_block = sample["factoid-subset"]["per_mode"]["abstracts"]
    his_keys = {k for k in his_block if k != "per_question"}
    assert his_keys <= set(REFERENCE_KEY_MAP), his_keys - set(REFERENCE_KEY_MAP)
    assert {REFERENCE_KEY_MAP[k] for k in his_keys} <= set(agg)
    # his metric vocabulary is kept verbatim; only the bare counters are spelled out
    assert REFERENCE_KEY_MAP["hit_rate"] == "hit_rate"
    assert REFERENCE_KEY_MAP["n"] == "n_questions"
    ours = {
        "retrieved_evidence_hit_rate", "retrieved_evidence_mean_recall",
        "n_refined_with_full_text", "n_answers_insufficient_context",
        "n_rejected_not_biomedical",
    }
    assert ours <= set(agg)


def test_rates_divide_by_all_questions_and_judge_means_by_judged_ones() -> None:
    results = [
        record(hit=True, recall=1.0, judge=(5, 4, 5)),
        record(hit=False, recall=0.0, judge=(1, 2, 3)),
        record(hit=True, recall=0.5, judge=None),  # not judged
        record(error="boom", hit=False, recall=0.0, judge=None, tokens=0),
    ]
    agg = aggregate(results)
    assert agg["n_questions"] == 4 and agg["n_questions_answered"] == 3
    assert agg["n_questions_errored"] == 1
    assert agg["hit_rate"] == 0.5 and agg["mean_recall"] == 0.375
    assert agg["n_questions_judged"] == 2
    assert agg["mean_judge"] == 3.0
    assert agg["mean_informativeness"] == 3.0 and agg["mean_clarity"] == 4.0


def test_token_and_elapsed_totals_follow_the_reference_layout() -> None:
    agg = aggregate([record(tokens=100, elapsed=10.0), record(tokens=300, elapsed=30.0)])
    assert agg["total_tokens"] == 400 and agg["mean_tokens"] == 200.0
    assert agg["total_input_tokens"] == 360 and agg["total_output_tokens"] == 30
    assert agg["total_reasoning_tokens"] == 10
    assert agg["mean_input_tokens"] == 180.0 and agg["mean_output_tokens"] == 15.0
    assert agg["total_elapsed_s"] == 40.0 and agg["mean_elapsed_s"] == 20.0
    assert agg["max_elapsed_s"] == 30.0
    # the judge's own usage is kept apart from the agent totals
    assert agg["total_judge_tokens"] == 100 and agg["mean_judge_tokens"] == 50.0
    assert agg["total_model_calls"] == 4


def test_pipeline_counters_are_summed() -> None:
    agg = aggregate([
        record(refined=True), record(insufficient=True), record(gate_rejected=True), record()
    ])
    assert agg["n_refined_with_full_text"] == 1
    assert agg["n_answers_insufficient_context"] == 1
    assert agg["n_rejected_not_biomedical"] == 1


def test_an_empty_mode_aggregates_without_dividing_by_zero() -> None:
    agg = aggregate([])
    assert agg["n_questions"] == 0 and agg["hit_rate"] == 0.0 and agg["mean_judge"] is None
    assert agg["mean_elapsed_s"] is None and agg["max_elapsed_s"] is None


# --- normalize ---------------------------------------------------------------------------


def _september_keys(rec: dict[str, Any]) -> dict[str, Any]:
    """The same record the way the harness wrote it between 2026-09-14 and 2026-09-23."""
    gate = rec["biological_relevance_check"]
    search, sel = rec["sentence_search"], rec["publication_selection"]
    fetch, depth = rec["publication_fetch"], rec["full_text_refinement"]
    return {
        "question": rec["question"],
        "reference": rec["reference_answers"],
        "generated": rec["generated_answer"],
        "error": rec["error"],
        "elapsed_s": rec["elapsed_s"],
        "gate": {"relevant": gate["is_biomedical_question"], "reason": gate["reason"]},
        "search": {
            "n_hits": search["n_sentences_returned"], "n_scored": search["n_sentences_scored"],
            "distinct_pmids": search["n_distinct_publications"],
            "best_score": search["best_relevance_score"],
            "worst_scored": search["worst_relevance_score"],
        },
        "selection": {
            "n_selected": sel["n_publications_selected"],
            "dropped_no_pmid": sel["n_dropped_without_pmid"],
            "dropped_below_min_score": sel["n_dropped_below_min_score"],
        },
        "fetch": {
            "n_fetched": fetch["n_publications_fetched"], "n_failed": fetch["n_fetch_failures"],
            "n_with_text": fetch["n_with_section_text"], "cited_pmids": rec["cited_pmids"],
        },
        "depth": {
            "sufficient": depth["answer_judged_sufficient"],
            "missing": depth["missing_information"], "refined": depth["refinement_applied"],
            "n_full_text": depth["n_publications_upgraded_to_full_text"],
        },
        "warnings": rec["answer_warnings"],
        "insufficient_context": rec["answer_insufficient_context"],
        "entities": rec["entities_in_cited_publications"],
        "overlap": {
            "hit": rec["answer_overlap"]["hit"], "recall": rec["answer_overlap"]["recall"],
            "matched": [], "missed": [],
        },
        "evidence_overlap": {"hit": True, "recall": 1.0, "matched": ["TP53"], "missed": []},
        "judge": rec["llm_judge"],
        "tokens": rec["agent_tokens"],
        "judge_tokens": rec["judge_tokens"],
        "id": rec["question_id"],
        "mode": "abstracts",
    }


def _legacy(rec: dict[str, Any]) -> dict[str, Any]:
    """A record the way the 2026-08 harness wrote it: `answer_overlap`, no `tokens`."""
    out = _september_keys(rec)
    out["answer_overlap"] = out.pop("overlap")
    del out["tokens"]
    del out["judge_tokens"]
    return out


def test_normalize_question_lifts_the_september_key_names_to_the_current_ones() -> None:
    lifted = normalize_question(_september_keys(record(refined=True)))
    assert list(lifted) == [k for k in QUESTION_KEYS if k != "previous_judges"]
    assert lifted == record(refined=True) | {"grounding_mode": "abstracts"}
    assert lifted["cited_pmids"] == [1]  # lifted out of the fetch block
    assert "cited_pmids" not in lifted["publication_fetch"]
    assert lifted["biological_relevance_check"] == {"is_biomedical_question": True, "reason": ""}
    assert lifted["full_text_refinement"]["refinement_applied"] is True
    assert lifted["answer_overlap"]["matched_items"] == []
    assert normalize_question(lifted) == lifted  # idempotent


def test_normalize_lifts_the_nested_aggregate_layout_and_recomputes() -> None:
    old = {
        "ds": {
            "modes": ["abstracts", "full_text"],
            "meta": {"model": "m", "offset": 0, "n": None},
            "per_mode": {
                "abstracts": {
                    "aggregate": {"answer_hit_rate": 0.0},
                    "per_question": [_legacy(record())],
                },
                "full_text": {"aggregate": {}, "per_question": [_legacy(record(hit=False))]},
            },
        }
    }
    new = normalize_results(old)
    block = new["ds"]
    assert list(block) == ["run_info", "grounding_modes", "results_by_grounding_mode"]
    assert block["run_info"] == {"model": "m", "question_offset": 0, "question_limit": None}
    assert block["grounding_modes"] == ["abstracts_only", "full_text_refinement"]
    abstracts = block["results_by_grounding_mode"]["abstracts_only"]
    assert "aggregate" not in abstracts
    assert abstracts["hit_rate"] == 1.0 and abstracts["mean_informativeness"] == 4.0
    q = abstracts["per_question"][0]
    assert q["answer_overlap"]["hit"] is True and q["grounding_mode"] == "abstracts_only"
    assert q["agent_tokens"]["total"] == 0  # unknown before capture
    assert block["results_by_grounding_mode"]["full_text_refinement"]["hit_rate"] == 0.0


def test_normalize_lifts_the_pre_modes_flat_layout() -> None:
    old = {"ds": {"aggregate": {}, "per_question": [_legacy(record())]}}
    new = normalize_results(old)
    assert new["ds"]["grounding_modes"] == ["abstracts_only"]
    assert new["ds"]["results_by_grounding_mode"]["abstracts_only"]["n_questions"] == 1


def test_normalize_is_idempotent_on_the_current_layout_and_keeps_run_info() -> None:
    current = {
        "ds": {
            "run_info": {"model": "m"},
            "grounding_modes": ["abstracts_only"],
            "results_by_grounding_mode": {
                "abstracts_only": {**aggregate([record()]), "per_question": [record()]}
            },
        }
    }
    assert normalize_results(current) == current


# --- report ------------------------------------------------------------------------------


def test_the_report_tabulates_every_metric_per_mode_and_side_by_side() -> None:
    results = normalize_results({
        "ds": {
            "run_info": {"model": "openai:x", "judge_model": "openai:x", "answer_style": "prose"},
            "grounding_modes": ["abstracts_only", "full_text_refinement"],
            "results_by_grounding_mode": {
                "abstracts_only": {"per_question": [record(judge=(3, 2, 4), tokens=100)]},
                "full_text_refinement": {
                    "per_question": [record(judge=(5, 4, 5), tokens=300, refined=True)]
                },
            },
        }
    })
    md = render_markdown([("run.json", results)])
    assert ("| dataset | grounding_mode | n_questions | answered | hit_rate | mean_recall | "
            "mean_judge |") in md
    assert "| mean_informativeness | mean_clarity |" in md
    assert "| ds | abstracts_only | 1 | 1/1 | 1.00 | 1.00 | 3.00 | 2.00 | 4.00 |" in md
    assert "| ds | full_text_refinement | 1 | 1/1 | 1.00 | 1.00 | 5.00 | 4.00 | 5.00 |" in md
    assert "## Abstracts only vs full-text refinement" in md
    assert "| mean informativeness (0-5) | 2.00 | 4.00 | +2.00 |" in md
    assert "| total tokens / Q | 100 | 300 | +200 |" in md
    assert "| abs hit | abs recall | abs judge | abs inf | abs clar | abs tok | abs flags |" in md
    abs_cells, ft_cells = "| 1 | 1.00 | 3 | 2 | 4 | 100 |  |", "| 1 | 1.00 | 5 | 4 | 5 | 300 | ft |"
    assert f"| 1 | Which gene? | 1 {abs_cells} {ft_cells[2:]}" in md
    assert "openai:x" in md and "RESULTS-SCHEMA.md" in md


def test_the_report_hides_token_columns_for_runs_made_before_usage_capture() -> None:
    results = normalize_results({
        "ds": {
            "modes": ["abstracts", "full_text"],
            "per_mode": {
                "abstracts": {"per_question": [_legacy(record())]},
                "full_text": {"per_question": [_legacy(record())]},
            },
        }
    })
    md = render_markdown([("old.json", results)])
    assert "tokens / Q" not in md.split("## Per question")[0].split("## Abstracts")[1]
    assert "| — |" in md  # the summary shows the missing token mean as —


# --- run folders -------------------------------------------------------------------------


def test_a_run_folder_renders_its_report_from_manifest_and_dataset_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260915-120000-gemini"
    run_dir.mkdir()
    block = {"grounding_modes": ["abstracts_only"], "run_info": {"model": "openai:g"},
             "results_by_grounding_mode": {
                 "abstracts_only": {"per_question": [record(tokens=200)]}}}
    (run_dir / "bioasq-list-100.json").write_text(json.dumps({"bioasq-list-100": block}))
    (run_dir / "bioasq-factoid-100.json").write_text(json.dumps({"bioasq-factoid-100": block}))
    (run_dir / "manifest.json").write_text(json.dumps({
        "label": "gemini", "model": "openai:g", "judge_model": "openai:g",
        "modes": ["abstracts"], "answer_style": "prose", "max_articles": 10,
        "offset": 0, "n": None, "started": "2026-09-15T12:00:00", "finished": None,
        "files": ["bioasq-factoid-100.json", "bioasq-list-100.json"],
    }))
    out = write_run_report(run_dir)
    md = out.read_text(encoding="utf-8")
    assert out == run_dir / "REPORT.md"
    assert "## Run" in md and "| model | openai:g |" in md
    assert "| grounding modes | abstracts_only |" in md  # an old manifest is lifted too
    assert "interrupted or still running" in md  # finished is None
    # manifest order wins over alphabetical, and the manifest itself is not a dataset
    assert md.index("| bioasq-factoid-100 |") < md.index("| bioasq-list-100 |")
    assert "manifest" not in md.split("## Runs")[1].split("## Summary")[0]
    assert "| 200 | 50 |" in md  # tokens/Q and judge tokens/Q in the summary row
