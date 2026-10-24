"""Re-score existing benchmark runs with a different LLM judge — no agent calls.

The team asked (2026-10-02) for the judge to be `meta-llama/llama-3.3-70b-instruct` on
the runs already delivered, without re-running the agent: every generated answer is
already in the JSON files, so only the `llm_judge` block (and its token usage) changes.
For each question with a generated answer the new judge is called with the same
prompts `run.py` uses; the previous verdict is kept under `previous_judges` so nothing
is lost; aggregates are recomputed; `run_info.judge_model`, the manifest and `REPORT.md`
are updated. Re-run `litsense.report --compare` (or the matrix launcher's `compare`)
afterwards for the cross-run report.

Datasets are written the moment they finish, so an interrupted run resumes: a dataset
whose `run_info.judge_model` already equals the target is skipped unless `--force`.

Usage:
    uv run python -m litsense.rejudge RUN_DIR [RUN_DIR ...] \\
        --judge-model openai:meta-llama/llama-3.3-70b-instruct [--concurrency 8] [--n 2]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from litsense.metrics import JUDGE_PROMPT_REVISION, Judge, Kind, judge_messages
from litsense.report import (
    aggregate,
    load_results,
    run_files,
    write_run_report,
)
from litsense.run import DATASETS, build_judge
from crossbar_llm.litsense_tools.models import TokenUsage

#: One judge call may not hang the run: a slow provider becomes a recorded error —
#: after `JUDGE_ATTEMPTS` tries, because under load OpenRouter queues llama calls for
#: minutes (28/200 timeouts at 120 s × 16 concurrent in the first pass).
JUDGE_TIMEOUT_S = 180.0
JUDGE_ATTEMPTS = 3


def needs_judging(q: dict[str, Any], before: str | None, target: str) -> bool:
    """Judge this record? Always when the judge changes; on a repeat pass only the
    records whose verdict is a recorded error (resume / `--retry-errors`)."""
    if before != target:
        return True
    verdict = q.get("llm_judge")
    return isinstance(verdict, dict) and "error" in verdict


def dataset_kind(name: str) -> Kind:
    """The reference kind (factoid/list) of a dataset, by registry name (seed suffixes
    and other decorations stripped), defaulting to `list`."""
    for key, ds in DATASETS.items():
        if name == key or name.startswith(key + "-") or name.startswith(key + "_"):
            kind: Kind = ds["kind"]
            return kind
    return "list"


async def judge_question(
    judge: Judge, q: dict[str, Any], kind: Kind, judge_model: str, sem: asyncio.Semaphore,
    progress: dict[str, int],
) -> None:
    """Replace one record's `llm_judge` / `judge_tokens`, keeping the previous verdict."""
    generated = q.get("generated_answer") or ""
    previous = q.get("llm_judge")
    before = q.pop("_judge_model_before", None)
    if previous is not None and before != judge_model and "error" not in previous:
        q.setdefault("previous_judges", []).append({
            "judge_model": before,
            "llm_judge": previous,
            "judge_tokens": q.get("judge_tokens"),
        })
    if not generated:
        q["llm_judge"] = None
        q["judge_tokens"] = TokenUsage().model_dump()
        return
    async with sem:
        last_error = "no attempt"
        for _attempt in range(JUDGE_ATTEMPTS):
            try:
                verdict, usage = await asyncio.wait_for(
                    judge(judge_messages(q["question"], generated, q["reference_answers"],
                                         kind=kind)),
                    timeout=JUDGE_TIMEOUT_S,
                )
                q["llm_judge"] = verdict.model_dump()
                q["judge_tokens"] = usage.model_dump()
                break
            except Exception as e:  # noqa: BLE001 — a failed grade is a recorded result
                last_error = f"{type(e).__name__}: {e}"
        else:
            q["llm_judge"] = {"error": last_error}
            q["judge_tokens"] = TokenUsage().model_dump()
        progress["done"] += 1
        if progress["done"] % 25 == 0 or progress["done"] == progress["total"]:
            print(f"    {progress['done']}/{progress['total']} judged", flush=True)


async def rejudge_file(
    path: Path, judge: Judge, judge_model: str, *, concurrency: int, limit: int | None,
    force: bool, retry_errors: bool = False, structured_output_method: str | None = None,
) -> dict[str, int]:
    results = load_results(path)
    stats = {"judged": 0, "skipped": 0, "errors": 0}
    sem = asyncio.Semaphore(concurrency)
    for name, block in results.items():
        info = block.setdefault("run_info", {})
        before = info.get("judge_model")
        if before == judge_model and not force and not retry_errors:
            print(f"  {name}: already judged by {judge_model}, skipped "
                  "(--retry-errors redoes its judge errors, --force everything)")
            stats["skipped"] += 1
            continue
        kind = dataset_kind(name)
        t0 = time.perf_counter()
        tasks = []
        selected: list[dict[str, Any]] = []
        for mode_block in block["results_by_grounding_mode"].values():
            questions = mode_block["per_question"]
            selected.extend(
                q for q in (questions[:limit] if limit is not None else questions)
                if force or needs_judging(q, before, judge_model)
            )
        if not selected:
            print(f"  {name}: nothing to judge")
            stats["skipped"] += 1
            continue
        progress = {"done": 0, "total": len(selected)}
        print(f"  {name}: judging {len(selected)} answers …", flush=True)
        for q in selected:
            q["_judge_model_before"] = before
            tasks.append(judge_question(judge, q, kind, judge_model, sem, progress))
        await asyncio.gather(*tasks)
        for mode, mode_block in block["results_by_grounding_mode"].items():
            questions = mode_block["per_question"]
            block["results_by_grounding_mode"][mode] = {
                **aggregate(questions), "per_question": questions
            }
            errors = sum(
                1 for q in questions if isinstance(q.get("llm_judge"), dict)
                and "error" in q["llm_judge"]
            )
            stats["errors"] += errors
            agg = block["results_by_grounding_mode"][mode]
            print(
                f"  {name} [{mode}]: judged {agg['n_questions_judged']}/{agg['n_questions']}"
                f" ({errors} judge errors) — mean_judge {agg['mean_judge']}, "
                f"informativeness {agg['mean_informativeness']}, clarity {agg['mean_clarity']}"
            )
        if before != judge_model:
            info["judge_model"] = judge_model
            info.setdefault("judge_history", []).append({
                "judge_model": before,
                "replaced_at": datetime.now().isoformat(timespec="seconds"),
            })
        info["judge_structured_output_method"] = structured_output_method
        info["judge_prompt_revision"] = JUDGE_PROMPT_REVISION
        stats["judged"] += len(tasks)
        print(f"  {name}: {len(tasks)} answers in {time.perf_counter() - t0:.0f}s")
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return stats


async def rejudge_run(
    run_dir: Path, judge: Judge, judge_model: str, *, concurrency: int, limit: int | None,
    force: bool, retry_errors: bool = False, structured_output_method: str | None = None,
) -> None:
    print(f"\n=== {run_dir.name} → judge {judge_model} ===")
    totals = {"judged": 0, "skipped": 0, "errors": 0}
    for path in run_files(run_dir):
        stats = await rejudge_file(
            path, judge, judge_model, concurrency=concurrency, limit=limit, force=force,
            retry_errors=retry_errors, structured_output_method=structured_output_method,
        )
        for k, v in stats.items():
            totals[k] += v
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("judge_model") != judge_model:
            manifest.setdefault("judge_history", []).append({
                "judge_model": manifest.get("judge_model"),
                "replaced_at": datetime.now().isoformat(timespec="seconds"),
            })
            manifest["judge_model"] = judge_model
        manifest["judge_structured_output_method"] = structured_output_method
        manifest["judge_prompt_revision"] = JUDGE_PROMPT_REVISION
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(f"  wrote {write_run_report(run_dir)}")
    print(f"  totals: {totals}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--judge-model", required=True,
                        help="provider-qualified judge, e.g. "
                        "openai:meta-llama/llama-3.3-70b-instruct")
    parser.add_argument("--structured-output", default=None,
                        choices=("json_schema", "function_calling", "json_mode"),
                        help="LangChain structured-output method for the judge model. "
                        "llama-3.3-70b via OpenRouter needs function_calling: its "
                        "JSON-schema route started producing runaway completions "
                        "(2026-10-02)")
    parser.add_argument("--concurrency", type=int, default=12,
                        help="parallel judge calls (the judge never touches NCBI)")
    parser.add_argument("--n", type=int, default=None,
                        help="only the first N questions per mode (smoke test)")
    parser.add_argument("--force", action="store_true",
                        help="re-judge every answer, even those this model already judged")
    parser.add_argument("--retry-errors", action="store_true",
                        help="on datasets this model already judged, redo only the answers "
                        "whose verdict is a recorded error (timeouts etc.)")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    async def run_all() -> None:
        # Built inside the running loop: the provider's async HTTP client binds to the
        # loop it is first used on, and one created before `asyncio.run` never answers.
        judge = build_judge(args.judge_model, method=args.structured_output)
        for run_dir in args.run_dirs:
            if not (run_dir / "manifest.json").exists():
                print(f"skipped {run_dir}: no manifest.json")
                continue
            await rejudge_run(
                run_dir, judge, args.judge_model, concurrency=args.concurrency,
                limit=args.n, force=args.force, retry_errors=args.retry_errors,
                structured_output_method=args.structured_output,
            )

    asyncio.run(run_all())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
