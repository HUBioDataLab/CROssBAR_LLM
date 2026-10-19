from typing_extensions import Self
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from threading import Lock
from collections import defaultdict
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver

from crossbar_llm.api.core.settings import Settings

@dataclass
class ChatSessionContext:
    session_id: str
    browser_id: str
    pending_resume: bool = False
    pending_cypher: str | None = None
    # The orchestrator's routing plan for a question paused at Cypher review:
    # the agents that still have to run once the Cypher is approved.
    pending_plan: Any | None = None
    # Recent (question, answer) turns, so the router can turn a follow-up such
    # as "what about its side effects?" into a question the literature agents,
    # which keep no history of their own, can answer.
    history: list[Any] = field(default_factory=list)
    # True while a question or resume is being answered. Two requests on one
    # session would share its LangGraph thread and bill every agent twice.
    busy: bool = False
    checkpointer: MemorySaver = field(default_factory=MemorySaver)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SessionLimitExceededError(Exception):
    def __init__(self, limit: int):
        super().__init__(f"Maximum number of concurrent sessions exceeded. You can only have {limit} active sessions at a time.")
        self.limit = limit

class SessionNotFoundError(Exception):
    def __init__(self, session_id: str):
        super().__init__(f"Session with ID {session_id} not found.")
        self.session_id = session_id

class SessionStore:
    def __init__(self, ttl_minutes: int, max_sessions_per_user: int):
        self._sessions: dict[str, ChatSessionContext] = {}
        self._browser_sessions: dict[str, list[str]] = defaultdict(list)
        self._max_sessions_per_user = max_sessions_per_user
        self._ttl = timedelta(minutes=ttl_minutes)
        self._lock = Lock()
    

    def create_session(self, browser_id: str) -> ChatSessionContext:
        with self._lock:
            self._cleanup_expired_sessions()
        
            session_ids = self._browser_sessions[browser_id]
            if len(session_ids) >= self._max_sessions_per_user:
                raise SessionLimitExceededError(limit=self._max_sessions_per_user)
            
            session = ChatSessionContext(
                session_id=str(uuid4()),
                browser_id=browser_id
            )

            self._sessions[session.session_id] = session
            self._browser_sessions[browser_id].append(session.session_id)

            return session
        
    def _get_session_locked(self, session_id: str, browser_id: str) -> ChatSessionContext:
        session = self._sessions.get(session_id)
        if not session:
            raise SessionNotFoundError(session_id=session_id)
        
        if session.browser_id != browser_id:
            raise ValueError(f"Session ID {session_id} does not belong to the provided browser ID.")
        
        return session

    def get_session(self, session_id: str, browser_id: str) -> ChatSessionContext:
        with self._lock:
            session = self._get_session_locked(session_id, browser_id)
            session.updated_at = datetime.now(UTC)

            self._cleanup_expired_sessions()
            return session
        
   
    def delete_session(self, session_id: str, browser_id: str) -> None:
        with self._lock:
            self._get_session_locked(session_id, browser_id)
            
            self._sessions.pop(session_id, None)
            browser_sessions = self._browser_sessions.get(browser_id, [])
            
            if session_id in browser_sessions:
                browser_sessions.remove(session_id)
            
            if not browser_sessions:
                self._browser_sessions.pop(browser_id, None)
    

    def _cleanup_expired_sessions(self):
        now = datetime.now(UTC)
        expired_sessions = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.updated_at > self._ttl
        ]

        for session_id in expired_sessions:
            session = self._sessions.pop(session_id, None)
            if not session:
                raise SessionNotFoundError(session_id=session_id)
            
            browser_sessions = self._browser_sessions.get(session.browser_id, [])
            if session_id in browser_sessions:
                browser_sessions.remove(session_id)
            
            if not browser_sessions:
                self._browser_sessions.pop(session.browser_id, None)
    
    def mark_resume_pending(
            self,
            session_id: str,
            browser_id: str,
            pending: bool,
            pending_cypher: str | None = None,
            pending_plan: Any | None = None,
        ) -> None:
        with self._lock:
            session = self._get_session_locked(session_id=session_id, browser_id=browser_id)
            session.pending_resume = pending
            session.pending_cypher = pending_cypher
            session.pending_plan = pending_plan if pending else None
            session.updated_at = datetime.now(UTC)

            self._cleanup_expired_sessions()

    def claim(self, session_id: str, browser_id: str) -> bool:
        """Mark the session busy. False if another request already holds it."""
        with self._lock:
            session = self._get_session_locked(session_id=session_id, browser_id=browser_id)
            if session.busy:
                return False
            session.busy = True
            return True

    def release(self, session_id: str, browser_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.browser_id == browser_id:
                session.busy = False

    def record_turn(self, session_id: str, browser_id: str, turn: Any, max_turns: int) -> None:
        with self._lock:
            session = self._get_session_locked(session_id=session_id, browser_id=browser_id)
            # Rebound rather than appended in place: a request that read the
            # history earlier keeps the snapshot it read.
            session.history = [*session.history, turn][-max_turns:] if max_turns > 0 else []
            session.updated_at = datetime.now(UTC)

    def __len__(self):
        with self._lock:
            return len(self._sessions)

    def _repr__(self):
        return f"{type(self).__name__}(max_sessions_per_user={self._max_sessions_per_user}, ttl={self._ttl})"
    
    def __call__(self) -> Self:
        return self
    
    def __bool__(self) -> bool:
        return True


session_store = SessionStore(
    ttl_minutes=Settings().session_ttl_minutes,
    max_sessions_per_user=Settings().max_sessions_per_user
)
