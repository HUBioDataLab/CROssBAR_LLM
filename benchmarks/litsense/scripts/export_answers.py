"""Flatten every benchmark run into one CSV of LLM outputs — one row per question × mode.

The result JSONs hold everything the models produced (generated answer, cited PMIDs,
relevance-check verdict and reason, depth-evaluator verdict, judge scores and rationale),
but one file per dataset per run is awkward for a reviewer who wants to scan the
answers. This writes a single spreadsheet-friendly CSV (UTF-8 with BOM, so Excel opens
it correctly) over any number of run folders.

Usage:
    uv run python litsense/scripts/export_answers.py OUT.csv RUN_DIR [RUN_DIR ...]
    uv run python litsense/scripts/export_answers.py all_answers.csv litsense/results/matrix/runs/*
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from litsense.report import load_run  # noqa: E402

COLUMNS = [
    "run", "model", "reasoning_effort", "judge_model", "dataset", "grounding_mode",
    "question_id", "question", "reference_answers", "generated_answer", "cited_pmids",
    "answer_insufficient_context", "is_biomedical_question", "relevance_reason",
    "answer_judged_sufficient", "missing_information", "refinement_applied",
    "overlap_hit", "overlap_recall", "overlap_matched_items", "overlap_missed_items",
    "judge_score", "judge_informativeness", "judge_clarity", "judge_matched_items",
    "judge_missed_items", "judge_rationale", "agent_tokens_total", "elapsed_s", "error",
]


def _join(items: Any) -> str:
    return " | ".join(str(i) for i in items) if isinstance(items, list) else ""


def rows_for_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    m = run["manifest"]
    rows: list[dict[str, Any]] = []
    for dataset, block in run["results"].items():
        for mode, mode_block in block["results_by_grounding_mode"].items():
            for q in mode_block["per_question"]:
                gate = q.get("biological_relevance_check") or {}
                depth = q.get("full_text_refinement") or {}
                overlap = q.get("answer_overlap") or {}
                judge = q.get("llm_judge") or {}
                rows.append({
                    "run": run["label"],
                    "model": m.get("model"),
                    "reasoning_effort": m.get("reasoning_effort"),
                    "judge_model": m.get("judge_model"),
                    "dataset": dataset,
                    "grounding_mode": mode,
                    "question_id": q.get("question_id"),
                    "question": q.get("question"),
                    "reference_answers": _join(q.get("reference_answers")),
                    "generated_answer": q.get("generated_answer"),
                    "cited_pmids": _join(q.get("cited_pmids")),
                    "answer_insufficient_context": q.get("answer_insufficient_context"),
                    "is_biomedical_question": gate.get("is_biomedical_question"),
                    "relevance_reason": gate.get("reason"),
                    "answer_judged_sufficient": depth.get("answer_judged_sufficient"),
                    "missing_information": depth.get("missing_information"),
                    "refinement_applied": depth.get("refinement_applied"),
                    "overlap_hit": overlap.get("hit"),
                    "overlap_recall": overlap.get("recall"),
                    "overlap_matched_items": _join(overlap.get("matched_items")),
                    "overlap_missed_items": _join(overlap.get("missed_items")),
                    "judge_score": judge.get("score"),
                    "judge_informativeness": judge.get("informativeness"),
                    "judge_clarity": judge.get("clarity"),
                    "judge_matched_items": _join(judge.get("matched_items")),
                    "judge_missed_items": _join(judge.get("missed_items")),
                    "judge_rationale": judge.get("rationale") or judge.get("error"),
                    "agent_tokens_total": (q.get("agent_tokens") or {}).get("total"),
                    "elapsed_s": q.get("elapsed_s"),
                    "error": q.get("error"),
                })
    return rows


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    out, run_dirs = Path(argv[1]), [Path(p) for p in argv[2:]]
    rows: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        if not (run_dir / "manifest.json").exists():
            print(f"skipped {run_dir} (no manifest.json)")
            continue
        rows.extend(rows_for_run(load_run(run_dir)))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out} ({len(rows)} rows from {len(run_dirs)} run folders)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
