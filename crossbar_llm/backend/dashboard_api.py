"""
Dashboard API for CROssBAR LLM Log Visualization.

Provides endpoints for authentication, log querying, statistics,
and real-time log streaming for the standalone log dashboard.
"""

import asyncio
import json
import logging
import os
import queue
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import jwt
import bcrypt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DASHBOARD_PASSWORD_HASH = os.getenv("DASHBOARD_PASSWORD_HASH", "")
DASHBOARD_JWT_SECRET = os.getenv("DASHBOARD_JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# Log directories – handle both flat and structured subdirectory layouts
_backend_dir = os.path.dirname(os.path.realpath(__file__))
LOGS_DIR = os.path.join(_backend_dir, "logs")
STRUCTURED_LOGS_DIR = os.path.join(LOGS_DIR, "structured_logs")
DETAILED_LOGS_DIR = os.path.join(LOGS_DIR, "detailed_logs")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

security = HTTPBearer()


def create_jwt(data: dict) -> str:
    payload = {
        **data,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, DASHBOARD_JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, DASHBOARD_JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    return verify_jwt(credentials.credentials)


# ---------------------------------------------------------------------------
# Log file reader
# ---------------------------------------------------------------------------


class LogFileReader:
    """Reads and queries structured log files (JSONL + JSON)."""

    def __init__(self) -> None:
        self._cache: Dict[str, List[dict]] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = 30  # seconds

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

    def _all_entries(self) -> List[dict]:
        """Return all log entries across all files."""
        all_entries: List[dict] = []
        for path in self._find_jsonl_files():
            all_entries.extend(self._read_jsonl(path))
        return all_entries

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
            # Include the entire day
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
        """Get a single log entry by request_id."""
        # Try detailed log file first
        for directory in [DETAILED_LOGS_DIR, LOGS_DIR]:
            path = os.path.join(directory, f"{request_id}.json")
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        # Fallback: search JSONL files
        for entry in self._all_entries():
            if entry.get("request_id") == request_id:
                return entry
        return None

    def get_stats(self, days: int = 30) -> Dict[str, Any]:
        """Compute aggregate statistics."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        entries = [e for e in self._all_entries() if (e.get("timestamp") or "") >= cutoff]

        total = len(entries)
        completed = sum(1 for e in entries if e.get("status") == "completed")
        failed = sum(1 for e in entries if e.get("status") == "failed")
        durations = [e.get("total_duration_ms", 0) for e in entries if e.get("total_duration_ms")]
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
        entries = [e for e in self._all_entries() if (e.get("timestamp") or "") >= cutoff_iso]

        buckets: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"total": 0, "completed": 0, "failed": 0, "tokens": 0, "duration_sum": 0}
        )

        for e in entries:
            ts = e.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                continue

            if granularity == "hour":
                key = dt.strftime("%Y-%m-%dT%H:00:00")
            elif granularity == "day":
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
                    "avg_duration_ms": round(b["duration_sum"] / b["total"], 1) if b["total"] else 0,
                }
            )
        return result

    def get_filters(self) -> Dict[str, List[str]]:
        """Return unique filter values."""
        entries = self._all_entries()
        models = sorted({e.get("model_name", "") for e in entries if e.get("model_name")})
        providers = sorted({e.get("provider", "") for e in entries if e.get("provider")})
        statuses = sorted({e.get("status", "") for e in entries if e.get("status")})
        search_types = sorted({e.get("search_type", "") for e in entries if e.get("search_type")})
        return {
            "models": models,
            "providers": providers,
            "statuses": statuses,
            "search_types": search_types,
        }

    def get_model_distribution(self, days: int = 30) -> List[Dict[str, Any]]:
        """Return model usage distribution."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        entries = [e for e in self._all_entries() if (e.get("timestamp") or "") >= cutoff]
        counts: Dict[str, int] = defaultdict(int)
        for e in entries:
            model = e.get("model_name", "unknown")
            counts[model] += 1
        return [{"model": m, "count": c} for m, c in sorted(counts.items(), key=lambda x: -x[1])]

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
# Dashboard log stream queue (separate from the main app's queue)
# ---------------------------------------------------------------------------

dashboard_log_queue: asyncio.Queue = asyncio.Queue()


class DashboardLogHandler(logging.Handler):
    """Captures log records and feeds them to the dashboard SSE stream."""

    def __init__(self) -> None:
        super().__init__()
        self._sync_queue: queue.Queue = queue.Queue()
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        if not self._running:
            return
        entry = self.format(record)
        self._sync_queue.put(entry)

    def _worker(self) -> None:
        while self._running:
            try:
                entry = self._sync_queue.get(timeout=0.5)
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.call_soon_threadsafe(dashboard_log_queue.put_nowait, entry)
                except RuntimeError:
                    pass
                self._sync_queue.task_done()
            except queue.Empty:
                continue

    def close(self) -> None:
        self._running = False
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        super().close()


def setup_dashboard_log_handler() -> None:
    """Attach the dashboard log handler to the root logger."""
    root = logging.getLogger()
    already = any(isinstance(h, DashboardLogHandler) for h in root.handlers)
    if not already:
        handler = DashboardLogHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        root.addHandler(handler)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# -- Auth -----------------------------------------------------------------

@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    if not DASHBOARD_PASSWORD_HASH:
        raise HTTPException(status_code=500, detail="Dashboard password not configured")

    password_bytes = body.password.encode("utf-8")
    hash_bytes = DASHBOARD_PASSWORD_HASH.encode("utf-8")

    if not bcrypt.checkpw(password_bytes, hash_bytes):
        raise HTTPException(status_code=401, detail="Invalid password")

    token = create_jwt({"sub": "dashboard_user"})
    return LoginResponse(token=token)


@router.get("/auth/verify")
async def verify_token(user: dict = Depends(get_current_user)):
    return {"valid": True}


# -- Stats ----------------------------------------------------------------

@router.get("/api/stats")
async def get_stats(
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    reader = get_reader()
    stats = reader.get_stats(days)
    stats["model_distribution"] = reader.get_model_distribution(days)
    stats["recent_errors"] = reader.get_recent_errors()
    return stats


@router.get("/api/stats/timeline")
async def get_timeline(
    days: int = Query(7, ge=1, le=365),
    granularity: str = Query("hour", regex="^(hour|day)$"),
    user: dict = Depends(get_current_user),
):
    return get_reader().get_timeline(days, granularity)


# -- Logs -----------------------------------------------------------------

@router.get("/api/logs")
async def get_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_by: str = Query("timestamp"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    user: dict = Depends(get_current_user),
):
    return get_reader().get_logs(
        page=page,
        limit=limit,
        status=status,
        model=model,
        provider=provider,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/api/logs/{request_id}")
async def get_log_detail(request_id: str, user: dict = Depends(get_current_user)):
    entry = get_reader().get_log_detail(request_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return entry


# -- Filters --------------------------------------------------------------

@router.get("/api/filters")
async def get_filters(user: dict = Depends(get_current_user)):
    return get_reader().get_filters()


# -- Live stream ----------------------------------------------------------

@router.get("/api/stream")
async def dashboard_stream(request: Request):
    """SSE endpoint for real-time log streaming.

    Accepts JWT via query param ``token`` so that EventSource (which cannot
    set headers) can authenticate.
    """
    token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing token query parameter")
    verify_jwt(token)

    async def event_generator():
        while True:
            try:
                entry = await asyncio.wait_for(dashboard_log_queue.get(), timeout=30)
                yield {"event": "log", "data": json.dumps({"log": entry})}
            except asyncio.TimeoutError:
                # Send keepalive comment to prevent connection timeout
                yield {"event": "ping", "data": ""}

    return EventSourceResponse(event_generator())
