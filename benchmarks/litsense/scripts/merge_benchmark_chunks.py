"""Merge chunked benchmark result files into one canonical results JSON.

Counterpart of `litsense.run --offset/--n`: when a long run is executed as several
chunks, this stitches the chunk outputs back into the exact shape a single full run
would have written (per-question lists concatenated in argument order, aggregates
recomputed over the merged lists).

Usage:
    uv run python litsense/scripts/merge_benchmark_chunks.py OUT.json CHUNK1.json CHUNK2.json ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from litsense.report import aggregate, normalize_results  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    out_path, chunk_paths = Path(argv[1]), [Path(p) for p in argv[2:]]

    merged: dict[str, Any] = {}
    for path in chunk_paths:
        chunk = normalize_results(json.loads(path.read_text(encoding="utf-8")))
        for dataset, payload in chunk.items():
            modes = payload["grounding_modes"]
            slot = merged.setdefault(
                dataset, {"grounding_modes": modes, "results_by_grounding_mode": {}}
            )
            if slot["grounding_modes"] != modes:
                print(f"{path}: mode list {modes} != {slot['grounding_modes']}")
                return 1
            if "run_info" in payload and "run_info" not in slot:
                # The first chunk's metadata stands for the run; offset/limit are per chunk.
                slot["run_info"] = {
                    **payload["run_info"], "question_offset": 0, "question_limit": None,
                    "chunked": True,
                }
            for mode, block in payload["results_by_grounding_mode"].items():
                slot["results_by_grounding_mode"].setdefault(mode, {"per_question": []})[
                    "per_question"
                ].extend(block["per_question"])

    for dataset, payload in merged.items():
        by_mode = payload["results_by_grounding_mode"]
        for mode, block in by_mode.items():
            questions = block["per_question"]
            by_mode[mode] = {**aggregate(questions), "per_question": questions}
            print(f"{dataset} [{mode}]: {len(questions)} questions merged")
        if "run_info" in payload:  # keep run_info first, like run.py writes it
            merged[dataset] = {"run_info": payload.pop("run_info"), **payload}

    out_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
