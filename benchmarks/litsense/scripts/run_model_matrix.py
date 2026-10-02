"""Launch, watch and collect the multi-model benchmark matrix.

One detached `litsense.run` process per model configuration in `benchmarks/models.json`,
all started at once so the matrix takes as long as its slowest member, not the sum. The
processes share the on-disk NCBI response cache (ADR-010, `--http-cache`), so between
them they make one request per URL to NCBI; the LLM calls are the only thing that runs
fifteen-fold. Everything the matrix produces lands in **one folder**,
`litsense/results/matrix/` (`--matrix-dir`): every row's run folder under `runs/<stamp>-
<label>/` (dataset JSONs, manifest, run.log, REPORT.md, pricing.json) and the cross-model
comparison next to them (`COMPARISON.md` + `comparison.json`). `compare` renders over
every run folder in the matrix folder, so rows finished on different days (or moved in by
hand) join the same report. This script only records which pid went where.

Usage (from the repo root, `.env` holding the OpenRouter key):

    uv run python litsense/scripts/run_model_matrix.py launch                  # the whole matrix
    uv run python litsense/scripts/run_model_matrix.py launch --only gpt-5.4,glm-5.2
    uv run python litsense/scripts/run_model_matrix.py launch --smoke          # 1 question, 1 set
                                                                      # → results/smoke/
    uv run python litsense/scripts/run_model_matrix.py status [STATE.json]     # progress per process
    uv run python litsense/scripts/run_model_matrix.py stop   [STATE.json]     # kill what is running
    uv run python litsense/scripts/run_model_matrix.py pricing [STATE.json]    # pricing.json per run
    uv run python litsense/scripts/run_model_matrix.py compare [--extra RUN_DIR ...]
                                                            # → results/matrix/COMPARISON.md
    uv run python litsense/scripts/run_model_matrix.py launch --then-compare
                                    # + a detached waiter that renders the comparison at the end

State files live in `benchmarks/.launcher/` (gitignored): `<stamp>.json` plus one
`<stamp>-<label>.out` per process (its raw stdout/stderr, in case a run dies before
`run.log` exists). The newest state file is the default for every command.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

BENCH = Path(__file__).resolve().parents[1]  # benchmarks/litsense
PROJECT = BENCH.parent  # the benchmarks uv project (cwd for `-m litsense.run`)
MODELS_FILE = BENCH / "models.json"
RUNS_DIR = BENCH / "results" / "runs"
MATRIX_DIR = BENCH / "results" / "matrix"
SMOKE_DIR = BENCH / "results" / "smoke"
STATE_DIR = BENCH / ".launcher"
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"

QUESTION_LINE = re.compile(r"^\[(\d+)/(\d+)\] Q: ")
DATASET_LINE = re.compile(r"^=== (\S+) \((\d+) questions")


# ---------------------------------------------------------------------------
# registry + state
# ---------------------------------------------------------------------------


def load_registry() -> dict[str, Any]:
    return dict(json.loads(MODELS_FILE.read_text(encoding="utf-8")))


def state_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    candidates = sorted(STATE_DIR.glob("*.json"))
    if not candidates:
        sys.exit(f"no launcher state in {STATE_DIR}; run `launch` first")
    return candidates[-1]


def load_state(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# launch
# ---------------------------------------------------------------------------


def run_command(
    entry: dict[str, Any], args: argparse.Namespace, judge_model: str, runs_dir: Path
) -> list[str]:
    cmd = [
        sys.executable, "-m", "litsense.run",
        "--mode", args.mode,
        "--http-cache",
        "--run-name", entry["label"] + (args.label_suffix or ""),
        "--runs-dir", str(runs_dir),
    ]
    if not args.no_judge:
        cmd += ["--judge", "--judge-model", judge_model]
    if entry.get("reasoning"):
        cmd += ["--reasoning", entry["reasoning"]]
    if entry.get("structured_output"):
        cmd += ["--structured-output", entry["structured_output"]]
    if entry.get("provider_order"):
        cmd += ["--provider-order", entry["provider_order"]]
    if args.smoke:
        cmd += ["--dataset", "bioasq-factoid-100", "--n", "1"]
    else:
        cmd += ["--dataset", args.dataset]
        if args.n is not None:
            cmd += ["--n", str(args.n)]
    return cmd


def spawn(cmd: list[str], model: str, out_path: Path) -> int:
    env = {**os.environ, "LITSENSE_MODEL": model, "PYTHONUTF8": "1"}
    out = out_path.open("ab")
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        cmd, cwd=PROJECT, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
        **kwargs,
    )
    return proc.pid


def cmd_launch(args: argparse.Namespace) -> int:
    registry = load_registry()
    judge_model = args.judge_model or registry["judge_model"]
    entries = registry["models"]
    if args.only:
        wanted = {label.strip() for label in args.only.split(",")}
        unknown = wanted - {e["label"] for e in entries}
        if unknown:
            sys.exit(f"unknown labels: {sorted(unknown)}")
        entries = [e for e in entries if e["label"] in wanted]
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    matrix_dir = Path(args.matrix_dir).resolve()
    runs_dir = SMOKE_DIR if args.smoke else matrix_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    state: dict[str, Any] = {
        "stamp": stamp,
        "started": datetime.now().isoformat(timespec="seconds"),
        "matrix_dir": str(matrix_dir),
        "runs_dir": str(runs_dir),
        "judge_model": None if args.no_judge else judge_model,
        "mode": args.mode,
        "smoke": args.smoke,
        "dataset": "bioasq-factoid-100" if args.smoke else args.dataset,
        "n": 1 if args.smoke else args.n,
        "processes": [],
    }
    path = STATE_DIR / f"{stamp}.json"
    for entry in entries:
        cmd = run_command(entry, args, judge_model, runs_dir)
        out_path = STATE_DIR / f"{stamp}-{entry['label']}{args.label_suffix or ''}.out"
        launched_at = datetime.now().isoformat(timespec="seconds")
        pid = spawn(cmd, entry["model"], out_path)
        state["processes"].append({
            "label": entry["label"] + (args.label_suffix or ""),
            "model": entry["model"],
            "reasoning": entry.get("reasoning"),
            "structured_output": entry.get("structured_output"),
            "provider_order": entry.get("provider_order"),
            "pid": pid,
            "launched": launched_at,
            "stdout": str(out_path),
            "command": cmd,
        })
        save_state(path, state)
        print(f"launched {entry['label']:36s} pid={pid:<7d} {entry['model']}"
              f"{' reasoning=' + entry['reasoning'] if entry.get('reasoning') else ''}")
        time.sleep(args.stagger)
    if args.then_compare is not None:
        pid = spawn_waiter(path, args.then_compare)
        state["waiter_pid"] = pid
        save_state(path, state)
        print(f"waiter pid={pid}: renders {matrix_dir / 'COMPARISON.md'} when every run "
              "has finished")
    print(f"\nruns: {runs_dir}\nstate: {path}\n"
          "watch: uv run python litsense/scripts/run_model_matrix.py status")
    return 0


# ---------------------------------------------------------------------------
# status / stop
# ---------------------------------------------------------------------------


def pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def find_run_dir(label: str, launched: str, runs_dir: Path = RUNS_DIR) -> Path | None:
    """The run folder `litsense.run` created for this label after `launched`."""
    stamp = datetime.fromisoformat(launched).strftime("%Y%m%d-%H%M%S")
    matches = sorted(
        d for d in runs_dir.glob(f"*-{label}")
        if d.is_dir() and d.name[:15] >= stamp[:15]
    )
    return matches[-1] if matches else None


def state_runs_dir(state: dict[str, Any]) -> Path:
    return Path(state.get("runs_dir") or RUNS_DIR)


def state_matrix_dir(state: dict[str, Any] | None, override: str | None = None) -> Path:
    if override:
        return Path(override).resolve()
    if state and state.get("matrix_dir"):
        return Path(state["matrix_dir"])
    return MATRIX_DIR


def matrix_run_dirs(matrix_dir: Path) -> list[Path]:
    """Every run folder (has a manifest) under `<matrix>/runs/`, oldest first."""
    runs = matrix_dir / "runs"
    if not runs.is_dir():
        return []
    return sorted(d for d in runs.iterdir() if d.is_dir() and (d / "manifest.json").exists())


def progress(run_dir: Path | None) -> dict[str, Any]:
    info: dict[str, Any] = {
        "run_dir": None, "dataset": None, "question": None, "of": None,
        "datasets_done": 0, "finished": None, "errors": 0, "last": "",
    }
    if run_dir is None:
        return info
    info["run_dir"] = run_dir.name
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        info["datasets_done"] = len(manifest.get("files", []))
        info["finished"] = manifest.get("finished")
    log = run_dir / "run.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines:
            m = DATASET_LINE.match(line)
            if m:
                info["dataset"] = m.group(1)
            m = QUESTION_LINE.match(line)
            if m:
                info["question"], info["of"] = int(m.group(1)), int(m.group(2))
            if line.startswith("  [ERROR]"):
                info["errors"] += 1
        info["last"] = lines[-1][:80] if lines else ""
    return info


def cmd_status(args: argparse.Namespace) -> int:
    path = state_path(args.state)
    state = load_state(path)
    print(f"state {path.name}  judge={state['judge_model']}  mode={state['mode']}  "
          f"dataset={state['dataset']}  n={state['n']}\n")
    header = f"{'label':36s} {'pid':>7s} {'alive':5s} {'dataset':30s} {'q':>7s} " \
             f"{'done':>4s} {'err':>3s} finished"
    print(header)
    for proc in state["processes"]:
        run_dir = find_run_dir(proc["label"], proc["launched"], state_runs_dir(state))
        info = progress(run_dir)
        alive = pid_alive(proc["pid"])
        q = f"{info['question']}/{info['of']}" if info["question"] else "—"
        print(f"{proc['label']:36s} {proc['pid']:7d} {'yes' if alive else 'no':5s} "
              f"{str(info['dataset'] or '—'):30s} {q:>7s} {info['datasets_done']:4d} "
              f"{info['errors']:3d} {info['finished'] or '—'}")
        if not alive and not info["finished"]:
            out = Path(proc["stdout"])
            tail = out.read_text(encoding="utf-8", errors="replace").splitlines()[-3:] \
                if out.exists() else []
            for line in tail:
                print(f"{'':36s}   | {line[:100]}")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    state = load_state(state_path(args.state))
    for proc in state["processes"]:
        if pid_alive(proc["pid"]):
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(proc["pid"]), "/T", "/F"],
                               capture_output=True)
            else:
                os.kill(proc["pid"], 15)
            print(f"stopped {proc['label']} (pid {proc['pid']})")
    return 0


# ---------------------------------------------------------------------------
# pricing / compare
# ---------------------------------------------------------------------------


def fetch_pricing() -> dict[str, dict[str, Any]]:
    """OpenRouter's per-token USD prices, keyed by model id (`openai:` prefix stripped)."""
    with urllib.request.urlopen(OPENROUTER_MODELS, timeout=30) as resp:  # noqa: S310
        data = json.loads(resp.read().decode("utf-8"))["data"]
    return {
        m["id"]: {
            "prompt": m["pricing"].get("prompt"),
            "completion": m["pricing"].get("completion"),
        }
        for m in data if m.get("pricing")
    }


def model_id(model_string: str | None) -> str | None:
    return None if not model_string else model_string.split(":", 1)[-1]


def write_pricing(run_dir: Path, prices: dict[str, dict[str, Any]]) -> bool:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    agent = prices.get(model_id(manifest.get("model")) or "")
    judge = prices.get(model_id(manifest.get("judge_model")) or "")
    if agent is None:
        return False
    (run_dir / "pricing.json").write_text(json.dumps({
        "source": OPENROUTER_MODELS,
        "fetched": datetime.now().isoformat(timespec="seconds"),
        "units": "USD per token",
        "model": agent,
        "judge": judge,
    }, indent=2), encoding="utf-8")
    return True


def state_run_dirs(state: dict[str, Any]) -> list[Path]:
    dirs = []
    for proc in state["processes"]:
        run_dir = find_run_dir(proc["label"], proc["launched"], state_runs_dir(state))
        if run_dir is not None:
            dirs.append(run_dir)
    return dirs


def _optional_state(arg: str | None) -> dict[str, Any] | None:
    """The newest launcher state if one exists; `compare` works without any."""
    if arg:
        return load_state(Path(arg))
    candidates = sorted(STATE_DIR.glob("*.json"))
    return load_state(candidates[-1]) if candidates else None


def comparison_dirs(args: argparse.Namespace) -> tuple[Path, list[Path]]:
    """The matrix folder and every run folder the comparison covers: all runs inside the
    matrix folder, the state's runs (if any) and `--extra`, deduplicated, in that order."""
    state = _optional_state(args.state)
    matrix_dir = state_matrix_dir(state, args.matrix_dir)
    dirs: list[Path] = []
    for run_dir in (
        matrix_run_dirs(matrix_dir)
        + (state_run_dirs(state) if state else [])
        + [Path(p) for p in args.extra]
    ):
        resolved = run_dir.resolve()
        if resolved not in dirs and resolved.is_dir():
            dirs.append(resolved)
    return matrix_dir, dirs


def cmd_pricing(args: argparse.Namespace) -> int:
    _, dirs = comparison_dirs(args)
    prices = fetch_pricing()
    for run_dir in dirs:
        print(f"{'priced' if write_pricing(run_dir, prices) else 'skipped'} {run_dir.name}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    matrix_dir, dirs = comparison_dirs(args)
    if not dirs:
        sys.exit(f"no run folders under {matrix_dir / 'runs'} (or in the state / --extra)")
    if not args.no_pricing:
        prices = fetch_pricing()
        for run_dir in dirs:
            if not (run_dir / "pricing.json").exists():
                write_pricing(run_dir, prices)
    sys.path.insert(0, str(PROJECT))
    from litsense.report import write_comparison  # noqa: PLC0415 — repo import after path fix

    out = args.output or matrix_dir / "COMPARISON.md"
    json_out = args.json or matrix_dir / "comparison.json"
    write_comparison(dirs, out, json_out=json_out)
    print(f"{len(dirs)} run folder(s) compared\nwrote {out}\nwrote {json_out}")
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    """Poll until every process of the state has finished, then render the comparison.

    Meant to run detached itself (`launch --then-compare` spawns it), so the comparison
    appears on disk without anyone watching.
    """
    path = state_path(args.state)
    while True:
        state = load_state(path)
        pending = []
        for proc in state["processes"]:
            info = progress(
                find_run_dir(proc["label"], proc["launched"], state_runs_dir(state))
            )
            if not info["finished"] and pid_alive(proc["pid"]):
                pending.append(proc["label"])
        if not pending:
            break
        print(f"{datetime.now().isoformat(timespec='seconds')} waiting on {len(pending)}: "
              f"{', '.join(pending)}", flush=True)
        time.sleep(args.poll)
    args.state = str(path)
    return cmd_compare(args)


def spawn_waiter(state_file: Path, extra: list[str]) -> int:
    cmd = [sys.executable, str(Path(__file__).resolve()), "wait", str(state_file)]
    if extra:
        cmd += ["--extra", *extra]
    out = STATE_DIR / f"{state_file.stem}-wait.out"
    return spawn(cmd, os.environ.get("LITSENSE_MODEL", "dry-run:not-connected"), out)


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    launch = sub.add_parser("launch", help="start one detached run per model configuration")
    launch.add_argument("--only", default=None, help="comma-separated labels to launch")
    launch.add_argument("--dataset", default="all")
    launch.add_argument("--n", type=int, default=None)
    launch.add_argument("--mode", default="both", choices=("abstracts", "full_text", "both"))
    launch.add_argument("--smoke", action="store_true",
                        help="one question of bioasq-factoid-100 per model: proves the model "
                        "id, structured output and reasoning switch before spending")
    launch.add_argument("--judge-model", default=None,
                        help="override benchmarks/models.json's fixed judge")
    launch.add_argument("--no-judge", action="store_true")
    launch.add_argument("--stagger", type=float, default=3.0,
                        help="seconds between process starts")
    launch.add_argument("--label-suffix", default=None,
                        help="appended to every run label, e.g. _seed48 when running "
                        "--dataset seed48 into its own --matrix-dir")
    launch.add_argument("--matrix-dir", default=str(MATRIX_DIR),
                        help="the folder that collects every run and the comparison "
                        f"(default {MATRIX_DIR})")
    launch.add_argument("--then-compare", nargs="*", default=None, metavar="RUN_DIR",
                        help="also start a detached waiter that renders the comparison "
                        "(pricing included) over every run in the matrix folder once "
                        "every process has finished; run folders outside the matrix "
                        "folder can be added as arguments")
    launch.set_defaults(func=cmd_launch)

    for name, func in (("status", cmd_status), ("stop", cmd_stop)):
        p = sub.add_parser(name)
        p.add_argument("state", nargs="?", default=None)
        p.set_defaults(func=func)

    for name, func, help_text in (
        ("pricing", cmd_pricing, "write pricing.json into each run folder"),
        ("compare", cmd_compare,
         "render the comparison over every run folder in the matrix folder"),
        ("wait", cmd_wait, "block until every run of the state finished, then compare"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("state", nargs="?", default=None)
        p.add_argument("--matrix-dir", default=None,
                       help=f"default: the state's matrix folder, else {MATRIX_DIR}")
        p.add_argument("--extra", nargs="*", default=[],
                       help="run folders outside the matrix folder to include")
        p.add_argument("-o", "--output", type=Path, default=None,
                       help="default <matrix-dir>/COMPARISON.md")
        p.add_argument("--json", type=Path, default=None,
                       help="default <matrix-dir>/comparison.json")
        p.add_argument("--no-pricing", action="store_true")
        p.add_argument("--poll", type=float, default=60.0, help="wait: seconds between checks")
        p.set_defaults(func=func)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
