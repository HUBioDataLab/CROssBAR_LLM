"""
Conversation Store for managing conversational memory.

This module provides a thread-safe in-memory store for conversation history,
enabling follow-up questions and contextual responses.
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """Represents a single turn in a conversation."""
    question: str
    cypher_query: str
    answer: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_context_string(self, include_cypher: bool = False) -> str:
        """Convert turn to a string for context injection."""
        if include_cypher and self.cypher_query:
            return f"User: {self.question}\nCypher: {self.cypher_query}\nAssistant: {self.answer}"
        return f"User: {self.question}\nAssistant: {self.answer}"


@dataclass
class Conversation:
    """Represents a full conversation session."""
    session_id: str
    turns: List[ConversationTurn] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    
    def update_access_time(self):
        """Update the last accessed timestamp."""
        self.last_accessed = datetime.now()


class ConversationStore:
    """
    Thread-safe in-memory store for conversation history.
    
    Features:
    - Stores conversation turns per session
    - Limits turns per session (sliding window)
    - TTL-based automatic cleanup of old sessions
    - Thread-safe operations
    """
    
    _instance: Optional['ConversationStore'] = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern to ensure one store instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(
        self,
        max_turns: int = 10,
        ttl_hours: int = 24,
        cleanup_interval_minutes: int = 30
    ):
        """
        Initialize the conversation store.
        
        Args:
            max_turns: Maximum number of turns to keep per session (sliding window)
            ttl_hours: Time-to-live for sessions in hours
            cleanup_interval_minutes: How often to run cleanup in minutes
        """
        if self._initialized:
            return
            
        self._store: Dict[str, Conversation] = {}
        self._store_lock = threading.Lock()
        self.max_turns = max_turns
        self.ttl_hours = ttl_hours
        self.cleanup_interval_minutes = cleanup_interval_minutes
        
        # Start background cleanup thread
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="ConversationStoreCleanup"
        )
        self._cleanup_thread.start()
        
        self._initialized = True
        logger.info(
            f"ConversationStore initialized with max_turns={max_turns}, "
            f"ttl_hours={ttl_hours}, cleanup_interval={cleanup_interval_minutes}min"
        )
    
    def _cleanup_loop(self):
        """Background loop to clean up expired sessions."""
        while True:
            time.sleep(self.cleanup_interval_minutes * 60)
            try:
                self._cleanup_expired_sessions()
            except Exception as e:
                logger.error(f"Error during conversation cleanup: {e}")
    
    def _cleanup_expired_sessions(self):
        """Remove sessions that have exceeded their TTL."""
        cutoff_time = datetime.now() - timedelta(hours=self.ttl_hours)
        expired_sessions = []
        
        with self._store_lock:
            for session_id, conversation in self._store.items():
                if conversation.last_accessed < cutoff_time:
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                del self._store[session_id]
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired conversation sessions")
    
    def add_turn(
        self,
        session_id: str,
        question: str,
        cypher_query: str,
        answer: str
    ) -> None:
        """
        Add a new turn to a conversation.
        
        Args:
            session_id: Unique session identifier
            question: User's question
            cypher_query: Generated Cypher query
            answer: Assistant's response
        """
        turn = ConversationTurn(
            question=question,
            cypher_query=cypher_query,
            answer=answer
        )
        
        with self._store_lock:
            if session_id not in self._store:
                self._store[session_id] = Conversation(session_id=session_id)
            
            conversation = self._store[session_id]
            conversation.turns.append(turn)
            conversation.update_access_time()
            
            # Trim to max_turns (sliding window)
            if len(conversation.turns) > self.max_turns:
                conversation.turns = conversation.turns[-self.max_turns:]
        
        logger.debug(
            f"Added turn to session {session_id[:8]}..., "
            f"total turns: {len(self._store[session_id].turns)}"
        )
    
    def get_history(self, session_id: str) -> List[ConversationTurn]:
        """
        Get conversation history for a session.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            List of conversation turns, or empty list if session not found
        """
        with self._store_lock:
            if session_id not in self._store:
                return []
            
            conversation = self._store[session_id]
            conversation.update_access_time()
            return list(conversation.turns)  # Return a copy
    
    def get_context_string(
        self,
        session_id: str,
        max_turns: Optional[int] = None,
        include_cypher: bool = False
    ) -> str:
        """
        Get conversation history formatted as a context string for prompts.
        
        Args:
            session_id: Unique session identifier
            max_turns: Maximum number of recent turns to include (None = all)
            include_cypher: Whether to include Cypher queries in context
            
        Returns:
            Formatted conversation context string
        """
        history = self.get_history(session_id)
        
        if not history:
            return ""
        
        if max_turns is not None:
            history = history[-max_turns:]
        
        context_parts = []
        for i, turn in enumerate(history, 1):
            context_parts.append(f"--- Previous Q&A {i} ---")
            context_parts.append(turn.to_context_string(include_cypher=include_cypher))
        
        return "\n".join(context_parts)
    
    def clear_session(self, session_id: str) -> bool:
        """
        Clear all history for a session.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            True if session was found and cleared, False otherwise
        """
        with self._store_lock:
            if session_id in self._store:
                del self._store[session_id]
                logger.info(f"Cleared session {session_id[:8]}...")
                return True
            return False
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """
        Get information about a session.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Dict with session info, or None if not found
        """
        with self._store_lock:
            if session_id not in self._store:
                return None
            
            conversation = self._store[session_id]
            return {
                "session_id": session_id,
                "turn_count": len(conversation.turns),
                "created_at": conversation.created_at.isoformat(),
                "last_accessed": conversation.last_accessed.isoformat()
            }
    
    def get_stats(self) -> Dict:
        """Get overall store statistics."""
        with self._store_lock:
            total_sessions = len(self._store)
            total_turns = sum(len(c.turns) for c in self._store.values())
            
            return {
                "total_sessions": total_sessions,
                "total_turns": total_turns,
                "max_turns_per_session": self.max_turns,
                "ttl_hours": self.ttl_hours
            }


# Global instance getter
def get_conversation_store() -> ConversationStore:
    """Get the global conversation store instance."""
    return ConversationStore()
