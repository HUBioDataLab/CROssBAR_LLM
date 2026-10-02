"""Results shape, aggregation and the structured report.

One place owns the benchmark **results contract**: the per-question record `run.py`
writes, the per-mode aggregate computed over it, and the Markdown report rendered from
either. The metric vocabulary follows Ahmet Oğuzhan's harness (see
`reference/paperclip_long.sample.json`, a trimmed copy of his real output) so both
agents' numbers sit in the same columns; every other key is named so that a reader
without repo context understands it (team feedback, 2026-09-24). The full key glossary
is `litsense/RESULTS-SCHEMA.md`; `REFERENCE_KEY_MAP` records which of his keys map to
which of ours.

Per dataset:
    {"run_info": {...}, "grounding_modes": [...], "results_by_grounding_mode": {
        "abstracts_only": {<aggregate keys…>, "per_question": [...]},
        "full_text_refinement": {...}}}

Everything here is pure and JSON-in / JSON-out, so it is unit-tested against synthetic
records and re-runnable over any result file ever written (older layouts and the
pre-2026-09-24 key names are lifted by `normalize_results`).

Runs live in folders (`litsense/results/runs/<stamp>-<label>/`, see `run.py`): one
`<dataset>.json` each, `manifest.json`, `run.log` and the `REPORT.md` rendered from them.

Usage:
    uv run python -m litsense.report litsense/results/runs/20260915-120000-gemini-2.5-flash
    uv run python -m litsense.report a.json b.json -o REPORT.md      # arbitrary files
    uv run python -m litsense.report old.json --rewrite            # lift to the current shape
    uv run python -m litsense.report --compare runs/a runs/b … -o COMPARISON.md
        # cross-run comparison: one row per run (model × reasoning), dataset × mode columns;
        # a `pricing.json` in a run folder (written by litsense/scripts/run_model_matrix.py) adds USD cost
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

#: Where the key glossary lives (recorded in every run's `run_info` and manifest).
SCHEMA_DOC = "litsense/RESULTS-SCHEMA.md"

#: The reference harness's per-mode keys → ours. Identity for the metric vocabulary
#: (hit_rate, mean_recall, mean_judge, …, token and elapsed totals); the two counters
#: whose bare names read wrong in context (`n` under a mode key looked like "100
#: abstracts") are spelled out. Pinned by a test against the sample file.
REFERENCE_KEY_MAP: dict[str, str] = {
    "n": "n_questions",
    "n_completed": "n_questions_answered",
    "hit_rate": "hit_rate",
    "mean_recall": "mean_recall",
    "mean_judge": "mean_judge",
    "mean_informativeness": "mean_informativeness",
    "mean_clarity": "mean_clarity",
    "total_tokens": "total_tokens",
    "mean_tokens": "mean_tokens",
    "total_input_tokens": "total_input_tokens",
    "total_output_tokens": "total_output_tokens",
    "total_reasoning_tokens": "total_reasoning_tokens",
    "mean_input_tokens": "mean_input_tokens",
    "mean_output_tokens": "mean_output_tokens",
    "total_elapsed_s": "total_elapsed_s",
    "mean_elapsed_s": "mean_elapsed_s",
    "max_elapsed_s": "max_elapsed_s",
}

#: Grounding modes as the harness runs them (`--mode abstracts|full_text`) → the keys the
#: results use. `abstracts_only`: answers grounded on abstracts. `full_text_refinement`:
#: the ADR-009 depth loop may swap cited abstracts for full text once.
GROUNDING_MODE_KEYS: dict[str, str] = {
    "abstracts": "abstracts_only",
    "full_text": "full_text_refinement",
}
MODE_SHORT = {"abstracts_only": "abs", "full_text_refinement": "ft"}

ZERO_TOKENS: dict[str, int] = {
    "input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "total": 0, "calls": 0
}

#: Where `run.py` puts run folders.
RUNS_DIR = Path(__file__).parent / "results" / "runs"

#: JSON files a run folder may hold that are not dataset results.
NON_RESULT_FILES = frozenset({"manifest.json", "pricing.json", "comparison.json"})

#: Per-question keys in the order they are written. Every key is documented in
#: `RESULTS-SCHEMA.md`; `normalize_question` emits exactly this order.
QUESTION_KEYS: tuple[str, ...] = (
    "question_id",
    "grounding_mode",
    "question",
    "reference_answers",
    "generated_answer",
    "cited_pmids",
    "answer_insufficient_context",
    "answer_warnings",
    "error",
    "elapsed_s",
    "biological_relevance_check",
    "sentence_search",
    "publication_selection",
    "publication_fetch",
    "full_text_refinement",
    "entities_in_cited_publications",
    "answer_overlap",
    "retrieved_evidence_overlap",
    "llm_judge",
    "agent_tokens",
    "judge_tokens",
    "previous_judges",  # only after litsense.rejudge replaced the judge
)

#: Pre-2026-09-24 per-question key → current key (top level). Applied by
#: `normalize_question`; idempotent because current keys are absent from the map or map
#: to themselves.
_QUESTION_KEY_RENAMES: dict[str, str] = {
    "id": "question_id",
    "mode": "grounding_mode",
    "reference": "reference_answers",
    "generated": "generated_answer",
    "warnings": "answer_warnings",
    "insufficient_context": "answer_insufficient_context",
    "gate": "biological_relevance_check",
    "search": "sentence_search",
    "selection": "publication_selection",
    "fetch": "publication_fetch",
    "depth": "full_text_refinement",
    "entities": "entities_in_cited_publications",
    "overlap": "answer_overlap",
    "evidence_overlap": "retrieved_evidence_overlap",
    "judge": "llm_judge",
    "tokens": "agent_tokens",
}

#: Same for the keys inside each group.
_NESTED_KEY_RENAMES: dict[str, dict[str, str]] = {
    "biological_relevance_check": {"relevant": "is_biomedical_question"},
    "sentence_search": {
        "n_hits": "n_sentences_returned",
        "n_scored": "n_sentences_scored",
        "distinct_pmids": "n_distinct_publications",
        "best_score": "best_relevance_score",
        "worst_scored": "worst_relevance_score",
    },
    "publication_selection": {
        "n_selected": "n_publications_selected",
        "dropped_no_pmid": "n_dropped_without_pmid",
        "dropped_below_min_score": "n_dropped_below_min_score",
    },
    "publication_fetch": {
        "n_fetched": "n_publications_fetched",
        "n_failed": "n_fetch_failures",
        "n_with_text": "n_with_section_text",
    },
    "full_text_refinement": {
        "sufficient": "answer_judged_sufficient",
        "missing": "missing_information",
        "refined": "refinement_applied",
        "n_full_text": "n_publications_upgraded_to_full_text",
    },
    "answer_overlap": {"matched": "matched_items", "missed": "missed_items"},
    "retrieved_evidence_overlap": {"matched": "matched_items", "missed": "missed_items"},
}

#: Pre-2026-09-24 `run_info` / manifest keys → current.
_RUN_INFO_RENAMES: dict[str, str] = {
    "modes": "grounding_modes",
    "offset": "question_offset",
    "n": "question_limit",
}


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------


def _mean_judge_field(results: list[dict[str, Any]], field: str) -> float | None:
    values = [
        r["llm_judge"][field]
        for r in results
        if isinstance(r.get("llm_judge"), dict)
        and isinstance(r["llm_judge"].get(field), int | float)
    ]
    return round(sum(values) / len(values), 2) if values else None


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll per-question records (current key set) into one mode's headline numbers.

    Reference-harness semantics: rates divide by every question run (an errored question
    counts as a miss); judge means average over the questions that were actually judged.
    """
    n = len(results) or 1
    tokens = [r.get("agent_tokens") or ZERO_TOKENS for r in results]
    judge_tokens = [r.get("judge_tokens") or ZERO_TOKENS for r in results]
    total_judge = sum(t.get("total", 0) for t in judge_tokens)
    elapsed = [r["elapsed_s"] for r in results if r.get("elapsed_s") is not None]
    total_in = sum(t.get("input", 0) for t in tokens)
    total_out = sum(t.get("output", 0) for t in tokens)
    total_tokens = sum(t.get("total", 0) for t in tokens)
    total_elapsed = sum(elapsed)
    return {
        "n_questions": len(results),
        "n_questions_answered": sum(
            1 for r in results if r.get("generated_answer") and not r.get("error")
        ),
        "hit_rate": round(sum(bool(r["answer_overlap"]["hit"]) for r in results) / n, 3),
        "mean_recall": round(sum(r["answer_overlap"]["recall"] for r in results) / n, 3),
        "mean_judge": _mean_judge_field(results, "score"),
        "mean_informativeness": _mean_judge_field(results, "informativeness"),
        "mean_clarity": _mean_judge_field(results, "clarity"),
        "total_tokens": total_tokens,
        "mean_tokens": round(total_tokens / n, 1),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_reasoning_tokens": sum(t.get("reasoning", 0) for t in tokens),
        "mean_input_tokens": round(total_in / n, 1),
        "mean_output_tokens": round(total_out / n, 1),
        "total_elapsed_s": round(total_elapsed, 1),
        "mean_elapsed_s": round(total_elapsed / len(elapsed), 1) if elapsed else None,
        "max_elapsed_s": round(max(elapsed), 1) if elapsed else None,
        # --- this harness's additions ---
        "total_model_calls": sum(t.get("calls", 0) for t in tokens),
        "total_judge_tokens": total_judge,
        "mean_judge_tokens": round(total_judge / n, 1),
        "n_questions_judged": sum(
            1 for r in results
            if isinstance(r.get("llm_judge"), dict) and "score" in r["llm_judge"]
        ),
        "n_questions_errored": sum(1 for r in results if r.get("error")),
        "n_rejected_not_biomedical": sum(
            1 for r in results
            if r.get("biological_relevance_check")
            and not r["biological_relevance_check"]["is_biomedical_question"]
        ),
        "n_refined_with_full_text": sum(
            1 for r in results
            if (r.get("full_text_refinement") or {}).get("refinement_applied")
        ),
        "n_answers_insufficient_context": sum(
            1 for r in results if r.get("answer_insufficient_context")
        ),
        "retrieved_evidence_hit_rate": round(
            sum(bool((r.get("retrieved_evidence_overlap") or {}).get("hit"))
                for r in results) / n,
            3,
        ),
        "retrieved_evidence_mean_recall": round(
            sum((r.get("retrieved_evidence_overlap") or {}).get("recall", 0.0)
                for r in results) / n,
            3,
        ),
    }


# ---------------------------------------------------------------------------
# shape normalization (every layout this harness ever wrote → the current one)
# ---------------------------------------------------------------------------


def _rename(mapping: dict[str, str], record: dict[str, Any]) -> dict[str, Any]:
    return {mapping.get(k, k): v for k, v in record.items()}


def normalize_question(record: dict[str, Any]) -> dict[str, Any]:
    """Lift one per-question record of any era to the current keys and order (idempotent)."""
    rec = _rename(_QUESTION_KEY_RENAMES, record)
    for group, mapping in _NESTED_KEY_RENAMES.items():
        if isinstance(rec.get(group), dict):
            rec[group] = _rename(mapping, rec[group])
    fetch = rec.get("publication_fetch")
    if isinstance(fetch, dict) and "cited_pmids" in fetch:
        rec.setdefault("cited_pmids", fetch.pop("cited_pmids"))  # lifted next to the answer
    rec.setdefault("cited_pmids", [])
    rec.setdefault("agent_tokens", dict(ZERO_TOKENS))
    rec["agent_tokens"].setdefault("calls", 0)
    rec.setdefault("judge_tokens", dict(ZERO_TOKENS))
    ordered = {key: rec[key] for key in QUESTION_KEYS if key in rec}
    ordered.update({k: v for k, v in rec.items() if k not in ordered})
    return ordered


def normalize_run_info(info: dict[str, Any]) -> dict[str, Any]:
    """Lift a `meta` / manifest block to the current key names (idempotent)."""
    out = _rename(_RUN_INFO_RENAMES, info)
    if isinstance(out.get("grounding_modes"), list):
        out["grounding_modes"] = [GROUNDING_MODE_KEYS.get(m, m) for m in out["grounding_modes"]]
    return out


def normalize_results(data: dict[str, Any]) -> dict[str, Any]:
    """Lift a results file of any era to the current contract, recomputing aggregates.

    Handles: the pre-`--mode both` flat layout (`{aggregate, per_question}` at dataset
    level), the nested `{per_mode: {mode: {aggregate, per_question}}}` layout, the
    2026-09 flat-per-mode layout with the old key names, and the current layout.
    Aggregates are always recomputed from the per-question records, so a file written
    before a metric existed gains it here.
    """
    out: dict[str, Any] = {}
    for name, block in data.items():
        if not isinstance(block, dict):
            out[name] = block
            continue
        if not any(k in block for k in ("per_mode", "results_by_grounding_mode")) \
                and "per_question" in block:
            block = {"modes": ["abstracts"], "per_mode": {"abstracts": block}}
        modes_in = block.get("results_by_grounding_mode") or block.get("per_mode") or {}
        by_mode: dict[str, Any] = {}
        for mode, mode_block in modes_in.items():
            key = GROUNDING_MODE_KEYS.get(mode, mode)
            questions = [normalize_question(q) for q in mode_block.get("per_question", [])]
            for q in questions:
                q["grounding_mode"] = key
            by_mode[key] = {**aggregate(questions), "per_question": questions}
        lifted: dict[str, Any] = {}
        info = block.get("run_info") or block.get("meta")
        if isinstance(info, dict):
            lifted["run_info"] = normalize_run_info(info)
        listed = block.get("grounding_modes") or block.get("modes") or list(by_mode)
        lifted["grounding_modes"] = [GROUNDING_MODE_KEYS.get(m, m) for m in listed]
        lifted["results_by_grounding_mode"] = by_mode
        out[name] = lifted
    return out


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def _f(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _tok(value: float | int | None) -> str:
    return "—" if not value else f"{int(value):,}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _truncate(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _run_date(file_name: str) -> str:
    """`20260828-crossbar-live-both.json` → `2026-08-28`; anything else stays as is."""
    stem = file_name[:8]
    if stem.isdigit():
        return f"{stem[:4]}-{stem[4:6]}-{stem[6:]}"
    return file_name


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _flags(q: dict[str, Any]) -> str:
    flags: list[str] = []
    gate = q.get("biological_relevance_check")
    if gate and not gate["is_biomedical_question"]:
        flags.append("gate")
    if q.get("answer_insufficient_context"):
        flags.append("ic")
    if (q.get("full_text_refinement") or {}).get("refinement_applied"):
        flags.append("ft")
    if q.get("error"):
        flags.append("err")
    return ",".join(flags) or ""


def _judge_cells(q: dict[str, Any]) -> tuple[str, str, str]:
    judge = q.get("llm_judge")
    if not isinstance(judge, dict) or "score" not in judge:
        return ("—", "—", "—")
    return (str(judge["score"]), str(judge.get("informativeness", "—")),
            str(judge.get("clarity", "—")))


def summary_rows(results: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for name, block in results.items():
        for mode in block["grounding_modes"]:
            a = block["results_by_grounding_mode"][mode]
            rows.append([
                name, mode, str(a["n_questions"]),
                f"{a['n_questions_answered']}/{a['n_questions']}",
                _f(a["hit_rate"]), _f(a["mean_recall"]),
                _f(a["mean_judge"]), _f(a["mean_informativeness"]), _f(a["mean_clarity"]),
                _f(a["retrieved_evidence_hit_rate"]), _f(a["retrieved_evidence_mean_recall"]),
                str(a["n_refined_with_full_text"]), str(a["n_answers_insufficient_context"]),
                _tok(a["mean_tokens"]), _tok(a["mean_judge_tokens"]),
                _f(a["mean_elapsed_s"], 1),
            ])
    return rows


SUMMARY_HEADER = [
    "dataset", "grounding_mode", "n_questions", "answered", "hit_rate", "mean_recall",
    "mean_judge", "mean_informativeness", "mean_clarity",
    "retrieved_evidence_hit_rate", "retrieved_evidence_mean_recall",
    "n_refined_with_full_text", "n_answers_insufficient_context",
    "tokens/Q", "judge tokens/Q", "mean_elapsed_s",
]

COMPARISON_METRICS: list[tuple[str, str, int]] = [
    ("hit_rate", "hit rate", 2),
    ("mean_recall", "mean recall", 2),
    ("mean_judge", "mean judge (0-5)", 2),
    ("mean_informativeness", "mean informativeness (0-5)", 2),
    ("mean_clarity", "mean clarity (0-5)", 2),
    ("n_refined_with_full_text", "questions refined with full text", 0),
    ("n_answers_insufficient_context", "insufficient-context answers", 0),
    ("mean_input_tokens", "input tokens / Q", 0),
    ("mean_output_tokens", "output tokens / Q", 0),
    ("mean_tokens", "total tokens / Q", 0),
    ("total_tokens", "total tokens", 0),
    ("mean_judge_tokens", "judge tokens / Q (not in totals)", 0),
    ("mean_elapsed_s", "mean response time (s)", 1),
]


def comparison_rows(a: dict[str, Any], b: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for key, label, digits in COMPARISON_METRICS:
        left, right = a.get(key), b.get(key)
        if key.endswith("tokens") and not (left or right):
            continue  # runs recorded before usage capture: no token columns
        delta = "—"
        if isinstance(left, int | float) and isinstance(right, int | float):
            delta = f"{right - left:+.{digits}f}"
        rows.append([label, _f(left, digits), _f(right, digits), delta])
    return rows


def per_question_table(block: dict[str, Any]) -> str:
    modes = block["grounding_modes"]
    header = ["#", "question", "ref"]
    for mode in modes:
        prefix = MODE_SHORT.get(mode, mode)
        header += [f"{prefix} hit", f"{prefix} recall", f"{prefix} judge",
                   f"{prefix} inf", f"{prefix} clar", f"{prefix} tok", f"{prefix} flags"]
    first = block["results_by_grounding_mode"][modes[0]]["per_question"]
    rows: list[list[str]] = []
    for i, q0 in enumerate(first):
        row = [str(i + 1), _truncate(q0["question"]), str(len(q0["reference_answers"]))]
        for mode in modes:
            qs = block["results_by_grounding_mode"][mode]["per_question"]
            if i >= len(qs):
                row += ["—"] * 7
                continue
            q = qs[i]
            score, inf, clar = _judge_cells(q)
            row += [
                "1" if q["answer_overlap"]["hit"] else "0", _f(q["answer_overlap"]["recall"]),
                score, inf, clar, _tok((q.get("agent_tokens") or {}).get("total")), _flags(q),
            ]
        rows.append(row)
    return _table(header, rows)


def render_markdown(
    runs: list[tuple[str, dict[str, Any]]], *, manifest: dict[str, Any] | None = None
) -> str:
    """The structured report over one or more normalized result files.

    `runs` pairs a source label (file name) with its normalized results; `manifest` is
    the run folder's manifest when rendering one run. Tables only — the numbers are the
    report; interpretation belongs in the accompanying message.
    """
    combined: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for label, results in runs:
        for name, block in results.items():
            key = name
            if key in combined:  # the same dataset run more than once: tell them apart
                key = f"{name} ({_run_date(label)})"
            combined[key] = block
            sources[key] = label

    lines = [
        "# LitSense agent — benchmark report",
        "",
        f"_Generated {date.today().isoformat()} by `litsense/report.py` from "
        f"{len(runs)} result file(s). Every number below is computed from the per-question "
        f"records in those files; nothing is hand-written. Key glossary: `{SCHEMA_DOC}`._",
        "",
        "**Metrics.** `hit_rate` / `mean_recall`: deterministic token overlap of the "
        "generated answer against the reference items (factoid: any item = hit; list: "
        "recall over items). `mean_judge` / `mean_informativeness` / `mean_clarity`: "
        "LLM-as-judge, 0–5 each — correctness against the reference, depth of explanation "
        "beyond the bare term, clarity of presentation (independent of correctness). "
        "`retrieved_evidence_*`: the same overlap applied to the retrieved abstracts/titles/"
        "sentences (the retrieval leg on its own). `tokens`: model usage per question over "
        "the agent's own calls (relevance check + synthesis + depth evaluator, as reported "
        "by the provider); the judge's own usage is listed separately as `judge tokens` and "
        "is not part of the agent totals. `grounding_mode`: `abstracts_only` = answers "
        "grounded on abstracts; `full_text_refinement` = the depth loop may swap cited "
        "abstracts for full text once. `n_refined_with_full_text`: questions where that "
        "loop fired; `n_answers_insufficient_context`: answers that declared the context "
        "insufficient.",
        "",
        *_manifest_lines(manifest),
        "## Runs",
        "",
        _table(
            ["dataset", "file", "model", "grounding modes", "judge", "answer_style"],
            [
                [
                    name, sources[name],
                    str((block.get("run_info") or {}).get("model", "—")),
                    "+".join(block["grounding_modes"]),
                    str((block.get("run_info") or {}).get("judge_model") or "—"),
                    str((block.get("run_info") or {}).get("answer_style", "—")),
                ]
                for name, block in combined.items()
            ],
        ),
        "",
        "## Summary",
        "",
        _table(SUMMARY_HEADER, summary_rows(combined)),
    ]

    both = {
        name: block for name, block in combined.items()
        if "abstracts_only" in block["results_by_grounding_mode"]
        and "full_text_refinement" in block["results_by_grounding_mode"]
    }
    if both:
        lines += ["", "## Abstracts only vs full-text refinement", ""]
        for name, block in both.items():
            lines += [
                f"### {name}", "",
                _table(
                    ["metric", "abstracts_only", "full_text_refinement", "Δ"],
                    comparison_rows(block["results_by_grounding_mode"]["abstracts_only"],
                                    block["results_by_grounding_mode"]["full_text_refinement"]),
                ),
                "",
            ]

    lines += ["## Per question", "",
              "_Per grounding mode (`abs` = abstracts_only, `ft` = full_text_refinement): "
              "`hit` (0/1) and `recall` from overlap; `judge`/`inf`/`clar` from the LLM "
              "judge (0–5, — when not judged); `tok` total agent tokens; `flags`: `gate` "
              "rejected as not a biomedical question, `ic` answer declared insufficient "
              "context, `ft` full-text refinement fired, `err` run error._", ""]
    for name, block in combined.items():
        lines += [f"### {name}", "", per_question_table(block), ""]
    return "\n".join(lines).rstrip() + "\n"


def _manifest_lines(manifest: dict[str, Any] | None) -> list[str]:
    if not manifest:
        return []
    m = normalize_run_info(manifest)
    limit = m.get("question_limit")
    rows = [
        ["label", str(m.get("label", "—"))],
        ["model", str(m.get("model", "—"))],
        ["judge model", str(m.get("judge_model") or "—")],
        ["grounding modes", "+".join(m.get("grounding_modes", []))],
        ["answer style", str(m.get("answer_style", "—"))],
        ["max articles", str(m.get("max_articles", "—"))],
        ["questions", "all" if limit is None else
         f"{limit} from offset {m.get('question_offset', 0)}"],
        ["started", str(m.get("started", "—"))],
        ["finished", str(m.get("finished") or "— (interrupted or still running)")],
    ]
    if m.get("note"):
        rows.append(["note", str(m["note"])])
    return ["## Run", "", _table(["field", "value"], rows), ""]


# ---------------------------------------------------------------------------
# cross-run comparison (the multi-model matrix)
# ---------------------------------------------------------------------------

#: Metrics tabulated per run in the comparison, with label and decimals.
COMPARE_METRICS: list[tuple[str, str, int]] = [
    ("hit_rate", "hit rate", 2),
    ("mean_recall", "mean recall", 2),
    ("mean_judge", "mean judge (0-5)", 2),
    ("mean_informativeness", "mean informativeness (0-5)", 2),
    ("mean_clarity", "mean clarity (0-5)", 2),
    ("n_answers_insufficient_context", "insufficient-context answers", 0),
    ("n_refined_with_full_text", "questions refined with full text", 0),
    ("n_questions_errored", "errors", 0),
    ("mean_tokens", "total tokens / Q", 0),
    ("mean_reasoning_tokens", "reasoning tokens / Q", 0),
    ("cost_usd", "agent cost (USD)", 2),
    ("mean_elapsed_s", "mean response time (s)", 1),
]


def load_run(run_dir: Path) -> dict[str, Any]:
    """One run folder → its manifest, pricing (if any) and normalized results per dataset."""
    manifest_path = run_dir / "manifest.json"
    manifest: dict[str, Any] = (
        normalize_run_info(json.loads(manifest_path.read_text(encoding="utf-8")))
        if manifest_path.exists() else {}
    )
    label = str(manifest.get("label") or run_dir.name)
    pricing_path = run_dir / "pricing.json"
    pricing: dict[str, Any] | None = (
        json.loads(pricing_path.read_text(encoding="utf-8")) if pricing_path.exists() else None
    )
    results: dict[str, Any] = {}
    for path in run_files(run_dir):
        results.update(load_results(path))
    return {
        "dir": str(run_dir),
        "label": label,
        "manifest": manifest,
        "pricing": pricing,
        "results": results,
    }


def _usd(tokens_in: int, tokens_out: int, price: dict[str, Any] | None) -> float | None:
    """USD for a token count at per-token prices (`prompt`/`completion`, OpenRouter's units)."""
    if not price:
        return None
    try:
        return tokens_in * float(price["prompt"]) + tokens_out * float(price["completion"])
    except (KeyError, TypeError, ValueError):
        return None


def compare_cell(run: dict[str, Any], dataset: str, mode: str) -> dict[str, Any] | None:
    """The aggregate of one run on one dataset × mode, plus derived cost/reasoning means."""
    block = run["results"].get(dataset)
    if not block or mode not in block["results_by_grounding_mode"]:
        return None
    mode_block = block["results_by_grounding_mode"][mode]
    agg = {k: v for k, v in mode_block.items() if k != "per_question"}
    questions = mode_block["per_question"]
    n = agg["n_questions"] or 1
    agg["mean_reasoning_tokens"] = round(agg["total_reasoning_tokens"] / n, 1)
    pricing = run["pricing"] or {}
    agg["cost_usd"] = _usd(
        agg["total_input_tokens"], agg["total_output_tokens"], pricing.get("model")
    )
    judge_in = sum((q.get("judge_tokens") or {}).get("input", 0) for q in questions)
    judge_out = sum((q.get("judge_tokens") or {}).get("output", 0) for q in questions)
    agg["judge_cost_usd"] = _usd(judge_in, judge_out, pricing.get("judge"))
    return agg


def _macro(cells: list[dict[str, Any]], key: str) -> float | None:
    values = [c[key] for c in cells if isinstance(c.get(key), int | float)]
    return sum(values) / len(values) if values else None


def _sum(cells: list[dict[str, Any]], key: str) -> float | None:
    values = [c[key] for c in cells if isinstance(c.get(key), int | float)]
    return sum(values) if values else None


def comparison_data(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """The JSON twin of the comparison report: every cell, no prose."""
    datasets: list[str] = []
    modes: list[str] = []
    for run in runs:
        for name, block in run["results"].items():
            if name not in datasets:
                datasets.append(name)
            for mode in block["grounding_modes"]:
                if mode not in modes:
                    modes.append(mode)
    cells: dict[str, dict[str, dict[str, Any]]] = {}
    for name in datasets:
        for mode in modes:
            for run in runs:
                cell = compare_cell(run, name, mode)
                if cell is not None:
                    cells.setdefault(name, {}).setdefault(mode, {})[run["label"]] = cell
    summary = []
    for run in runs:
        m = run["manifest"]
        own = [
            cells[d][mode][run["label"]]
            for d in datasets for mode in modes
            if run["label"] in cells.get(d, {}).get(mode, {})
        ]
        summary.append({
            "label": run["label"],
            "dir": run["dir"],
            "model": m.get("model"),
            "reasoning_effort": m.get("reasoning_effort"),
            "judge_model": m.get("judge_model"),
            "started": m.get("started"),
            "finished": m.get("finished"),
            "datasets": sorted({d for d in datasets if any(
                run["label"] in cells.get(d, {}).get(mode, {}) for mode in modes)}),
            "total_tokens": _sum(own, "total_tokens"),
            "cost_usd": _sum(own, "cost_usd"),
            "judge_cost_usd": _sum(own, "judge_cost_usd"),
        })
    return {
        "generated": date.today().isoformat(),
        "schema": SCHEMA_DOC,
        "datasets": datasets,
        "grounding_modes": modes,
        "runs": summary,
        "cells_by_dataset_mode_run": cells,
    }


def _run_name(run: dict[str, Any]) -> str:
    m = run["manifest"]
    reasoning = m.get("reasoning_effort")
    return str(run["label"]) + (f" (reasoning={reasoning})" if reasoning else "")


def _cost(value: float | None) -> str:
    return "—" if value is None else f"${value:.2f}"


def render_comparison(runs: list[dict[str, Any]]) -> str:
    """The cross-run report: runs table, macro-average leaderboard, one table per metric
    (run × dataset/mode), then the full per-dataset detail. Tables only, like `REPORT.md`."""
    data = comparison_data(runs)
    datasets, modes = data["datasets"], data["grounding_modes"]
    cells = data["cells_by_dataset_mode_run"]
    lines = [
        "# LitSense agent — multi-model comparison",
        "",
        f"_Generated {data['generated']} by `litsense/report.py --compare` from "
        f"{len(runs)} run folder(s). Every number is computed from the per-question records "
        f"in those folders; nothing is hand-written. Key glossary: `{SCHEMA_DOC}`._",
        "",
        "**Reading the tables.** One row per run = one model configuration (a model with "
        "or without a requested reasoning level). Columns pair each dataset with the "
        "grounding mode: `abs` = abstracts_only, `ft` = full_text_refinement (the depth "
        "loop may swap cited abstracts for full text once). Metrics are the same as in "
        "each run's `REPORT.md`: `hit rate` / `mean recall` are deterministic overlap of "
        "the answer with the reference items; `judge` / `informativeness` / `clarity` are "
        "the LLM judge's 0–5 scores (the judge model is listed per run — fix it across "
        "runs for a fair comparison); `tokens / Q` are the agent's own calls (relevance "
        "check + synthesis + depth evaluator; reasoning tokens included in output and also "
        "listed on their own); `cost` is those tokens at the prices recorded in the run's "
        "`pricing.json` when present (judge cost separate). `insufficient-context "
        "answers` counts answers that declined for lack of evidence.",
        "",
        "## Runs",
        "",
        _table(
            ["run", "model", "reasoning", "judge", "started", "finished", "datasets",
             "agent tokens", "agent cost", "judge cost"],
            [
                [
                    r["label"], str(r["model"] or "—"), str(r["reasoning_effort"] or "default"),
                    str(r["judge_model"] or "—"), str(r["started"] or "—"),
                    str(r["finished"] or "— (running/interrupted)"),
                    f"{len(r['datasets'])}/{len(datasets)}",
                    _tok(r["total_tokens"]), _cost(r["cost_usd"]), _cost(r["judge_cost_usd"]),
                ]
                for r in data["runs"]
            ],
        ),
        "",
    ]

    # Leaderboard: macro-average over the datasets every run completed, per mode.
    common = [
        d for d in datasets
        if all(any(run["label"] in cells.get(d, {}).get(mode, {}) for mode in modes)
               for run in runs)
    ]
    if common:
        lines += [
            "## Overview — macro-average over the datasets all runs completed",
            "",
            f"_Datasets averaged: {', '.join(common)}. Factoid and list sets are averaged "
            "together, so this is a leaderboard glance, not a metric; the per-dataset "
            "tables below are the measurement._",
            "",
        ]
        header = ["run"]
        for mode in modes:
            short = MODE_SHORT.get(mode, mode)
            header += [f"{short} hit", f"{short} recall", f"{short} judge", f"{short} inf",
                       f"{short} clar", f"{short} ic", f"{short} tok/Q", f"{short} cost"]
        rows = []
        for run in runs:
            row = [_run_name(run)]
            for mode in modes:
                own = [cells[d][mode][run["label"]] for d in common
                       if run["label"] in cells.get(d, {}).get(mode, {})]
                row += [
                    _f(_macro(own, "hit_rate")), _f(_macro(own, "mean_recall")),
                    _f(_macro(own, "mean_judge")), _f(_macro(own, "mean_informativeness")),
                    _f(_macro(own, "mean_clarity")),
                    _f(_sum(own, "n_answers_insufficient_context"), 0),
                    _tok(_macro(own, "mean_tokens")), _cost(_sum(own, "cost_usd")),
                ]
            rows.append(row)
        lines += [_table(header, rows), ""]

    lines += ["## Per metric — run × dataset", ""]
    for key, label, digits in COMPARE_METRICS:
        header = ["run"]
        for name in datasets:
            for mode in modes:
                header.append(f"{name} {MODE_SHORT.get(mode, mode)}")
        rows = []
        for run in runs:
            row = [_run_name(run)]
            for name in datasets:
                for mode in modes:
                    cell = cells.get(name, {}).get(mode, {}).get(run["label"])
                    value = None if cell is None else cell.get(key)
                    if key == "cost_usd":
                        row.append(_cost(value))
                    elif key.endswith("tokens"):
                        row.append(_tok(value))
                    else:
                        row.append(_f(value, digits))
            rows.append(row)
        lines += [f"### {label}", "", _table(header, rows), ""]

    lines += ["## Per dataset — every metric", ""]
    detail_header = [
        "run", "n_questions", "answered", "hit_rate", "mean_recall", "mean_judge",
        "mean_informativeness", "mean_clarity", "retrieved_evidence_hit_rate",
        "n_answers_insufficient_context", "n_refined_with_full_text", "n_questions_errored",
        "in tok/Q", "out tok/Q", "reasoning tok/Q", "tokens/Q",
        "agent cost", "judge tok/Q", "mean_elapsed_s",
    ]
    for name in datasets:
        for mode in modes:
            rows = []
            for run in runs:
                a = cells.get(name, {}).get(mode, {}).get(run["label"])
                if a is None:
                    continue
                rows.append([
                    _run_name(run), str(a["n_questions"]),
                    f"{a['n_questions_answered']}/{a['n_questions']}",
                    _f(a["hit_rate"]), _f(a["mean_recall"]), _f(a["mean_judge"]),
                    _f(a["mean_informativeness"]), _f(a["mean_clarity"]),
                    _f(a["retrieved_evidence_hit_rate"]),
                    str(a["n_answers_insufficient_context"]),
                    str(a["n_refined_with_full_text"]), str(a["n_questions_errored"]),
                    _tok(a["mean_input_tokens"]), _tok(a["mean_output_tokens"]),
                    _tok(a["mean_reasoning_tokens"]), _tok(a["mean_tokens"]),
                    _cost(a["cost_usd"]), _tok(a["mean_judge_tokens"]),
                    _f(a["mean_elapsed_s"], 1),
                ])
            if rows:
                lines += [f"### {name} — {mode}", "", _table(detail_header, rows), ""]
    return "\n".join(lines).rstrip() + "\n"


def load_runs(run_dirs: list[Path]) -> list[dict[str, Any]]:
    """Load run folders; two runs sharing a label are told apart by their folder name."""
    runs = [load_run(d) for d in run_dirs]
    seen: dict[str, int] = {}
    for run in runs:
        seen[run["label"]] = seen.get(run["label"], 0) + 1
    for run in runs:
        if seen[run["label"]] > 1:
            run["label"] = Path(run["dir"]).name
    return runs


def write_comparison(
    run_dirs: list[Path], out: Path, *, json_out: Path | None = None
) -> Path:
    runs = load_runs(run_dirs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_comparison(runs), encoding="utf-8")
    if json_out is not None:
        json_out.write_text(
            json.dumps(comparison_data(runs), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return out


# ---------------------------------------------------------------------------
# run folders + CLI
# ---------------------------------------------------------------------------


def load_results(path: Path) -> dict[str, Any]:
    return normalize_results(json.loads(path.read_text(encoding="utf-8")))


def run_files(run_dir: Path) -> list[Path]:
    """The dataset result files of a run folder, in the order the manifest lists them."""
    manifest_path = run_dir / "manifest.json"
    listed: list[str] = []
    if manifest_path.exists():
        listed = json.loads(manifest_path.read_text(encoding="utf-8")).get("files", [])
    ordered = [run_dir / f for f in listed if (run_dir / f).exists()]
    rest = sorted(
        p for p in run_dir.glob("*.json")
        if p.name not in NON_RESULT_FILES and p not in ordered
    )
    return ordered + rest


def is_run_dir(path: Path) -> bool:
    return path.is_dir() and (path / "manifest.json").exists()


def rewrite_run_dir(run_dir: Path) -> None:
    """Rewrite a run folder's JSON files (and manifest) in the current key set."""
    for path in run_files(run_dir):
        path.write_text(json.dumps(load_results(path), indent=2, ensure_ascii=False),
                        encoding="utf-8")
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = normalize_run_info(json.loads(manifest_path.read_text(encoding="utf-8")))
        manifest.setdefault("schema", SCHEMA_DOC)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                 encoding="utf-8")


def write_run_report(run_dir: Path) -> Path:
    """Render `REPORT.md` for one run folder from its JSON files and manifest."""
    manifest_path = run_dir / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    )
    runs = [(p.name, load_results(p)) for p in run_files(run_dir)]
    out = run_dir / "REPORT.md"
    out.write_text(render_markdown(runs, manifest=manifest), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the structured Markdown report from benchmark result files."
    )
    parser.add_argument("files", nargs="+", type=Path,
                        help="Result JSON files, or a single run folder.")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Write the report here (default: stdout).")
    parser.add_argument("--rewrite", action="store_true",
                        help="Also rewrite each input file in the current shape "
                        "(aggregates recomputed, older layouts and key names lifted).")
    parser.add_argument("--backfill-model", default=None,
                        help="With --rewrite: record this model string in files that carry "
                        "no run metadata (runs made before metadata was written).")
    parser.add_argument("--compare", action="store_true",
                        help="Treat every argument as a run folder and render the cross-run "
                        "comparison (one row per run) instead of per-run reports.")
    parser.add_argument("--json", type=Path, default=None,
                        help="With --compare: also write the comparison data as JSON here.")
    args = parser.parse_args(argv)

    if args.compare:
        missing = [str(d) for d in args.files if not d.is_dir()]
        if missing:
            print(f"--compare takes run folders; not folders: {missing}", file=sys.stderr)
            return 2
        if args.output is None:
            sys.stdout.write(render_comparison(load_runs(list(args.files))))
            return 0
        write_comparison(list(args.files), args.output, json_out=args.json)
        print(f"wrote {args.output}", file=sys.stderr)
        return 0

    if len(args.files) == 1 and args.files[0].is_dir():
        if args.rewrite:
            rewrite_run_dir(args.files[0])
        print(f"wrote {write_run_report(args.files[0])}", file=sys.stderr)
        return 0

    runs: list[tuple[str, dict[str, Any]]] = []
    for path in args.files:
        results = load_results(path)
        if args.rewrite:
            for block in results.values():
                if args.backfill_model and "run_info" not in block:
                    block["run_info"] = {"model": args.backfill_model, "backfilled": True}
            path.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                            encoding="utf-8")
            print(f"rewrote {path}", file=sys.stderr)
        runs.append((path.name, results))

    report = render_markdown(runs)
    if args.output is None:
        sys.stdout.write(report)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
