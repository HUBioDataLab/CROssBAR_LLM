"""
Dashboard API for CROssBAR LLM Log Visualization.

Provides endpoints for log querying and statistics for the standalone log dashboard.
"""

import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Log directories – handle both flat and structured subdirectory layouts
_backend_dir = os.path.dirname(os.path.realpath(__file__))
LOGS_DIR = os.path.join(_backend_dir, "logs")
STRUCTURED_LOGS_DIR = os.path.join(LOGS_DIR, "structured_logs")
DETAILED_LOGS_DIR = os.path.join(LOGS_DIR, "detailed_logs")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Log file reader
# ---------------------------------------------------------------------------

# Maximum time gap (seconds) between a db_search and its paired
# query_execution to be considered the same user action.
_PAIR_MAX_GAP_SECONDS = 120


def _merge_pair(gen_entry: dict, exec_entry: dict) -> dict:
    """Merge a db_search entry with its paired query_execution entry
    into a single combined log entry that represents the full pipeline."""

    merged = {**gen_entry}  # start with generation entry as base

    merged["search_type"] = "generate_and_execute"
    merged["linked_request_id"] = exec_entry.get("request_id", "")

    # Combine steps from both entries into one pipeline
    gen_steps = list(gen_entry.get("steps", []))
    exec_steps = list(exec_entry.get("steps", []))

    # Add query correction as a synthetic step if present
    qc = gen_entry.get("query_correction")
    if qc:
        qc_step = {
            "step_name": "query_correction",
            "step_number": len(gen_steps) + 1,
            "duration_ms": qc.get("duration_ms", 0),
            "status": "completed" if qc.get("success") else "failed",
            "details": {
                "schemas_checked": qc.get("schemas_checked", 0),
                "corrections_count": len(qc.get("corrections", [])),
                "success": qc.get("success"),
            },
        }
        gen_steps.append(qc_step)

    # Add Neo4j execution as a synthetic step if present
    neo = exec_entry.get("neo4j_execution")
    if neo:
        neo_step = {
            "step_name": "neo4j_execution",
            "step_number": len(gen_steps) + 1,
            "duration_ms": neo.get("execution_time_ms", 0),
            "status": "failed" if neo.get("error") else "completed",
            "details": {
                "result_count": neo.get("result_count", 0),
                "connection_status": neo.get("connection_status", ""),
            },
        }
        gen_steps.append(neo_step)

    # Re-number all exec steps following gen steps
    offset = len(gen_steps)
    for s in exec_steps:
        s = {**s, "step_number": offset + s.get("step_number", 1)}
        gen_steps.append(s)

    merged["steps"] = gen_steps

    # Combine LLM calls
    merged["llm_calls"] = list(gen_entry.get("llm_calls", [])) + list(
        exec_entry.get("llm_calls", [])
    )

    # Take execution-phase fields from the exec entry
    merged["neo4j_execution"] = exec_entry.get("neo4j_execution")
    merged["natural_language_response"] = exec_entry.get(
        "natural_language_response", ""
    )

    # Combined duration = generation + execution
    gen_dur = gen_entry.get("total_duration_ms", 0) or 0
    exec_dur = exec_entry.get("total_duration_ms", 0) or 0
    merged["total_duration_ms"] = gen_dur + exec_dur

    # Use the earliest start / latest end
    merged["start_time"] = gen_entry.get("start_time", "")
    merged["end_time"] = exec_entry.get("end_time", "") or gen_entry.get(
        "end_time", ""
    )

    # Worst status wins
    if exec_entry.get("status") == "failed" or gen_entry.get("status") == "failed":
        merged["status"] = "failed"
    else:
        merged["status"] = exec_entry.get("status", gen_entry.get("status", ""))

    # Carry over error from whichever entry has one
    if exec_entry.get("error"):
        merged["error"] = exec_entry["error"]
        merged["error_type"] = exec_entry.get("error_type")
        merged["error_traceback"] = exec_entry.get("error_traceback")
        merged["error_step"] = exec_entry.get("error_step")
    elif gen_entry.get("error"):
        pass  # already in merged from gen_entry copy

    return merged


class LogFileReader:
    """Reads and queries structured log files (JSONL + JSON)."""

    def __init__(self) -> None:
        self._cache: Dict[str, List[dict]] = {}
        self._cache_time: Dict[str, float] = {}
        self._merged_cache: Optional[List[dict]] = None
        self._merged_cache_key: Optional[str] = None

    # -- helpers ----------------------------------------------------------

    def _find_jsonl_files(self) -> List[str]:
        """Find all .jsonl log files in both log directories."""
        files = []
        for directory in [LOGS_DIR, STRUCTURED_LOGS_DIR]:
            if os.path.isdir(directory):
                for f in os.listdir(directory):
                    if f.endswith(".jsonl"):
                        full = os.path.join(directory, f)
                        if full not in files:
                            files.append(full)
        files.sort()
        return files

    def _read_jsonl(self, path: str) -> List[dict]:
        """Read and parse a JSONL file, with caching."""
        mtime = os.path.getmtime(path)
        cached_time = self._cache_time.get(path, 0)
        if path in self._cache and (mtime == cached_time):
            return self._cache[path]

        entries: List[dict] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}")

        self._cache[path] = entries
        self._cache_time[path] = mtime
        return entries

    def _raw_entries(self) -> List[dict]:
        """Return all raw (un-merged) log entries across all files."""
        all_entries: List[dict] = []
        for path in self._find_jsonl_files():
            all_entries.extend(self._read_jsonl(path))
        return all_entries

    def _cache_key(self) -> str:
        """Simple cache-busting key based on file mtimes."""
        parts = []
        for path in self._find_jsonl_files():
            try:
                parts.append(f"{path}:{os.path.getmtime(path)}")
            except OSError:
                pass
        return "|".join(parts)

    def _all_entries(self) -> List[dict]:
        """Return merged log entries (db_search + query_execution pairs
        combined into single entries)."""
        key = self._cache_key()
        if self._merged_cache is not None and self._merged_cache_key == key:
            return self._merged_cache

        raw = self._raw_entries()
        merged = self._pair_and_merge(raw)
        self._merged_cache = merged
        self._merged_cache_key = key
        return merged

    def _pair_and_merge(self, raw: List[dict]) -> List[dict]:
        """Walk through entries in order and pair consecutive
        db_search / query_execution entries that belong together."""

        # Index: for each db_search, try to find a matching query_execution
        # that immediately follows (same question, same client, same final_query).
        consumed: set = set()  # indices of entries consumed by pairing
        result: List[dict] = []

        for i, entry in enumerate(raw):
            if i in consumed:
                continue

            if entry.get("search_type") == "db_search" and i + 1 < len(raw):
                candidate = raw[i + 1]
                if self._is_pair(entry, candidate):
                    merged = _merge_pair(entry, candidate)
                    result.append(merged)
                    consumed.add(i)
                    consumed.add(i + 1)
                    continue

            result.append(entry)

        return result

    @staticmethod
    def _is_pair(gen: dict, exec_: dict) -> bool:
        """Check whether gen (db_search) and exec_ (query_execution) form a pair."""
        # Accept both query_execution and query_execution_with_retry
        exec_type = exec_.get("search_type", "")
        if exec_type not in ["query_execution", "query_execution_with_retry"]:
            return False
        
        # Strong pairing signal: same request_id
        gen_req_id = gen.get("request_id", "")
        exec_req_id = exec_.get("request_id", "")
        if gen_req_id and exec_req_id and gen_req_id == exec_req_id:
            return True
        
        # Fallback to legacy pairing logic
        if gen.get("question", "").strip() != exec_.get("question", "").strip():
            return False
        # Same client
        gen_client = gen.get("client_ip") or gen.get("client_id", "")
        exec_client = exec_.get("client_ip") or exec_.get("client_id", "")
        if gen_client != exec_client:
            return False
        # Same final_query
        gen_fq = (gen.get("final_query") or "").strip()
        exec_fq = (exec_.get("final_query") or "").strip()
        if gen_fq and exec_fq and gen_fq != exec_fq:
            return False
        # Time gap within threshold
        try:
            t1 = datetime.fromisoformat(gen.get("timestamp", ""))
            t2 = datetime.fromisoformat(exec_.get("timestamp", ""))
            if abs((t2 - t1).total_seconds()) > _PAIR_MAX_GAP_SECONDS:
                return False
        except (ValueError, TypeError):
            pass
        return True

    # -- public API -------------------------------------------------------

    def get_logs(
        self,
        page: int = 1,
        limit: int = 50,
        status: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        search: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        sort_by: str = "timestamp",
        sort_order: str = "desc",
        search_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        entries = self._all_entries()

        # -- filters --
        if status:
            entries = [e for e in entries if e.get("status") == status]
        if model:
            entries = [e for e in entries if e.get("model_name") == model]
        if provider:
            entries = [
                e
                for e in entries
                if (e.get("provider") or "").lower() == provider.lower()
            ]
        if search_type:
            entries = [e for e in entries if e.get("search_type") == search_type]
        if search:
            q = search.lower()
            entries = [
                e
                for e in entries
                if q in (e.get("question") or "").lower()
                or q in (e.get("request_id") or "").lower()
                or q in (e.get("generated_query") or "").lower()
                or q in (e.get("final_query") or "").lower()
            ]
        if date_from:
            entries = [
                e for e in entries if (e.get("timestamp") or "") >= date_from
            ]
        if date_to:
            date_to_end = date_to + "T23:59:59" if len(date_to) == 10 else date_to
            entries = [
                e for e in entries if (e.get("timestamp") or "") <= date_to_end
            ]

        total = len(entries)

        # -- sort --
        reverse = sort_order == "desc"
        entries.sort(key=lambda e: e.get(sort_by, ""), reverse=reverse)

        # -- paginate --
        start = (page - 1) * limit
        page_entries = entries[start : start + limit]

        return {
            "items": page_entries,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": max(1, (total + limit - 1) // limit),
        }

    def get_log_detail(self, request_id: str) -> Optional[dict]:
        """Get a single (merged) log entry by request_id."""
        # Search merged entries first (matches both original and linked IDs)
        for entry in self._all_entries():
            if entry.get("request_id") == request_id:
                return entry
            if entry.get("linked_request_id") == request_id:
                return entry

        # Try detailed log file
        for directory in [DETAILED_LOGS_DIR, LOGS_DIR]:
            path = os.path.join(directory, f"{request_id}.json")
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        return None

    def get_stats(self, days: int = 30) -> Dict[str, Any]:
        """Compute aggregate statistics over merged entries."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        entries = [
            e for e in self._all_entries() if (e.get("timestamp") or "") >= cutoff
        ]

        total = len(entries)
        completed = sum(1 for e in entries if e.get("status") == "completed")
        failed = sum(1 for e in entries if e.get("status") == "failed")
        durations = [
            e.get("total_duration_ms", 0)
            for e in entries
            if e.get("total_duration_ms")
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0

        total_tokens = 0
        for e in entries:
            for call in e.get("llm_calls", []):
                usage = call.get("token_usage") or {}
                total_tokens += usage.get("total_tokens", 0)

        return {
            "total_queries": total,
            "completed": completed,
            "failed": failed,
            "success_rate": round(completed / total * 100, 1) if total else 0,
            "avg_duration_ms": round(avg_duration, 1),
            "total_tokens": total_tokens,
            "period_days": days,
        }

    def get_timeline(
        self, days: int = 7, granularity: str = "hour"
    ) -> List[Dict[str, Any]]:
        """Return time-bucketed counts for charts."""
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()
        entries = [
            e
            for e in self._all_entries()
            if (e.get("timestamp") or "") >= cutoff_iso
        ]

        buckets: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "tokens": 0,
                "duration_sum": 0,
            }
        )

        for e in entries:
            ts = e.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                continue

            if granularity == "day":
                key = dt.strftime("%Y-%m-%d")
            else:
                key = dt.strftime("%Y-%m-%dT%H:00:00")

            buckets[key]["total"] += 1
            if e.get("status") == "completed":
                buckets[key]["completed"] += 1
            elif e.get("status") == "failed":
                buckets[key]["failed"] += 1
            buckets[key]["duration_sum"] += e.get("total_duration_ms", 0)
            for call in e.get("llm_calls", []):
                usage = call.get("token_usage") or {}
                buckets[key]["tokens"] += usage.get("total_tokens", 0)

        result = []
        for key in sorted(buckets.keys()):
            b = buckets[key]
            result.append(
                {
                    "time": key,
                    "total": b["total"],
                    "completed": b["completed"],
                    "failed": b["failed"],
                    "tokens": b["tokens"],
                    "avg_duration_ms": round(b["duration_sum"] / b["total"], 1)
                    if b["total"]
                    else 0,
                }
            )
        return result

    def get_filters(self) -> Dict[str, List[str]]:
        """Return unique filter values."""
        entries = self._all_entries()
        models = sorted(
            {e.get("model_name", "") for e in entries if e.get("model_name")}
        )
        providers = sorted(
            {e.get("provider", "") for e in entries if e.get("provider")}
        )
        statuses = sorted(
            {e.get("status", "") for e in entries if e.get("status")}
        )
        search_types = sorted(
            {e.get("search_type", "") for e in entries if e.get("search_type")}
        )
        return {
            "models": models,
            "providers": providers,
            "statuses": statuses,
            "search_types": search_types,
        }

    def get_model_distribution(self, days: int = 30) -> List[Dict[str, Any]]:
        """Return model usage distribution."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        entries = [
            e for e in self._all_entries() if (e.get("timestamp") or "") >= cutoff
        ]
        counts: Dict[str, int] = defaultdict(int)
        for e in entries:
            model = e.get("model_name", "unknown")
            counts[model] += 1
        return [
            {"model": m, "count": c}
            for m, c in sorted(counts.items(), key=lambda x: -x[1])
        ]

    def get_recent_errors(self, limit: int = 5) -> List[dict]:
        """Return the most recent failed entries."""
        entries = [e for e in self._all_entries() if e.get("status") == "failed"]
        entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return entries[:limit]


# Singleton reader
_reader: Optional[LogFileReader] = None


def get_reader() -> LogFileReader:
    global _reader
    if _reader is None:
        _reader = LogFileReader()
    return _reader


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# -- Stats ----------------------------------------------------------------


@router.get("/api/stats")
async def get_stats(days: int = Query(30, ge=1, le=365)):
    reader = get_reader()
    stats = await asyncio.to_thread(reader.get_stats, days)
    stats["model_distribution"] = await asyncio.to_thread(reader.get_model_distribution, days)
    stats["recent_errors"] = await asyncio.to_thread(reader.get_recent_errors)
    return stats


@router.get("/api/stats/timeline")
async def get_timeline(
    days: int = Query(7, ge=1, le=365),
    granularity: str = Query("hour", regex="^(hour|day)$"),
):
    return await asyncio.to_thread(get_reader().get_timeline, days, granularity)


# -- Logs -----------------------------------------------------------------


@router.get("/api/logs")
async def get_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    search: Optional[str] = None,
    search_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_by: str = Query("timestamp"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
):
    return await asyncio.to_thread(
        get_reader().get_logs,
        page=page,
        limit=limit,
        status=status,
        model=model,
        provider=provider,
        search=search,
        search_type=search_type,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/api/logs/{request_id}")
async def get_log_detail(request_id: str):
    entry = await asyncio.to_thread(get_reader().get_log_detail, request_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return entry


# -- Filters --------------------------------------------------------------


@router.get("/api/filters")
async def get_filters():
    return await asyncio.to_thread(get_reader().get_filters)
