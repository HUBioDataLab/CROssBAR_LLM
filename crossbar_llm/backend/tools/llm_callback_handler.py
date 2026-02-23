"""
Detailed LLM Callback Handler for CROssBAR LLM

This module provides a comprehensive callback handler for LangChain
that captures all LLM interactions including prompts, responses,
token usage, timing, and intermediate outputs (like chain-of-thought).
"""

import logging
from datetime import datetime, timezone
from time import time
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.messages import BaseMessage

from .structured_logger import (
    LLMCallLog,
    TokenUsage,
    get_structured_logger,
    log_llm_call,
)


class DetailedLLMCallback(BaseCallbackHandler):
    """
    Comprehensive callback handler for capturing LLM interactions.
    
    Captures:
    - Full prompts sent to the LLM
    - Raw responses (including thinking/reasoning for supported models)
    - Token usage statistics
    - Response timing
    - Streaming chunks
    """
    
    def __init__(
        self,
        call_type: str = "unknown",
        model_name: str = "",
        provider: str = ""
    ):
        """
        Initialize the callback handler.
        
        Args:
            call_type: Type of call (cypher_generation, qa_response, etc.)
            model_name: Name of the model being used
            provider: LLM provider name
        """
        super().__init__()
        self.call_type = call_type
        self.model_name = model_name
        self.provider = provider
        
        # Call tracking
        self.call_start_time: Optional[float] = None
        self.call_start_datetime: Optional[str] = None
        self.prompts: List[str] = []
        self.responses: List[str] = []
        self.thinking_content: List[str] = []
        self.streaming_chunks: List[str] = []
        
        # Token tracking
        self.input_tokens = 0
        self.output_tokens = 0
        
        # Current LLM call log
        self.current_log: Optional[LLMCallLog] = None
        
        # Logger instance
        self.logger = logging.getLogger(__name__)
    
    @property
    def always_verbose(self) -> bool:
        """Always capture all events."""
        return True
    
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM starts running."""
        self.call_start_time = time()
        self.call_start_datetime = datetime.now(timezone.utc).isoformat()
        self.prompts = prompts.copy()
        self.responses = []
        self.thinking_content = []
        self.streaming_chunks = []
        
        # Extract model info from serialized if available
        if serialized:
            if "name" in serialized:
                self.model_name = self.model_name or serialized.get("name", "")
            if "kwargs" in serialized:
                kwargs_data = serialized.get("kwargs", {})
                self.model_name = self.model_name or kwargs_data.get("model_name", "")
                self.model_name = self.model_name or kwargs_data.get("model", "")
        
        self.logger.info(
            f"[LLM_START] type={self.call_type} model={self.model_name} "
            f"provider={self.provider} prompt_count={len(prompts)}"
        )
        
        # Log full prompts at DEBUG level
        for i, prompt in enumerate(prompts):
            self.logger.debug(f"[LLM_PROMPT_{i}] {prompt[:500]}{'...' if len(prompt) > 500 else ''}")
    
    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when chat model starts running."""
        self.call_start_time = time()
        self.call_start_datetime = datetime.now(timezone.utc).isoformat()
        self.responses = []
        self.thinking_content = []
        self.streaming_chunks = []
        
        # Convert messages to string for logging
        self.prompts = []
        for message_list in messages:
            prompt_parts = []
            for msg in message_list:
                role = getattr(msg, "type", "unknown")
                content = getattr(msg, "content", str(msg))
                prompt_parts.append(f"[{role}]: {content}")
            self.prompts.append("\n".join(prompt_parts))
        
        # Extract model info
        if serialized:
            if "name" in serialized:
                self.model_name = self.model_name or serialized.get("name", "")
            if "kwargs" in serialized:
                kwargs_data = serialized.get("kwargs", {})
                self.model_name = self.model_name or kwargs_data.get("model_name", "")
                self.model_name = self.model_name or kwargs_data.get("model", "")
        
        self.logger.info(
            f"[CHAT_START] type={self.call_type} model={self.model_name} "
            f"provider={self.provider} message_count={len(messages)}"
        )
        
        # Log messages at DEBUG level
        for i, prompt in enumerate(self.prompts):
            self.logger.debug(f"[CHAT_PROMPT_{i}] {prompt[:1000]}{'...' if len(prompt) > 1000 else ''}")
    
    def on_llm_new_token(
        self,
        token: str,
        *,
        chunk: Optional[Any] = None,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a new token is streamed."""
        self.streaming_chunks.append(token)
        
        # Check for thinking/reasoning content in the chunk
        if chunk and hasattr(chunk, "message"):
            message = chunk.message
            # Handle Claude's thinking blocks
            if hasattr(message, "content") and isinstance(message.content, list):
                for block in message.content:
                    if hasattr(block, "type") and block.type == "thinking":
                        if hasattr(block, "thinking"):
                            self.thinking_content.append(block.thinking)
    
    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM ends running."""
        end_time = time()
        end_datetime = datetime.now(timezone.utc).isoformat()
        duration_ms = (end_time - self.call_start_time) * 1000 if self.call_start_time else 0
        
        # Extract responses
        for generation_list in response.generations:
            for generation in generation_list:
                response_text = generation.text if hasattr(generation, "text") else str(generation)
                self.responses.append(response_text)
                
                # Check for thinking content in response
                if hasattr(generation, "message"):
                    msg = generation.message
                    if hasattr(msg, "content") and isinstance(msg.content, list):
                        for block in msg.content:
                            if hasattr(block, "type") and block.type == "thinking":
                                if hasattr(block, "thinking"):
                                    self.thinking_content.append(block.thinking)
                    
                    # Also check additional_kwargs for reasoning
                    if hasattr(msg, "additional_kwargs"):
                        reasoning = msg.additional_kwargs.get("reasoning_content", "")
                        if reasoning:
                            self.thinking_content.append(reasoning)
        
        # Extract token usage from LLM output
        llm_output = response.llm_output or {}
        token_usage = llm_output.get("token_usage", {})
        
        if token_usage:
            self.input_tokens = token_usage.get("prompt_tokens", 0)
            self.output_tokens = token_usage.get("completion_tokens", 0)
        else:
            # Try alternative field names
            self.input_tokens = llm_output.get("input_tokens", 0)
            self.output_tokens = llm_output.get("output_tokens", 0)
        
        total_tokens = self.input_tokens + self.output_tokens
        
        # Create the LLM call log
        self.current_log = LLMCallLog(
            call_type=self.call_type,
            model_name=self.model_name,
            provider=self.provider,
            prompt="\n---\n".join(self.prompts),
            raw_response="\n---\n".join(self.responses),
            thinking_content="\n---\n".join(self.thinking_content) if self.thinking_content else "",
            token_usage=TokenUsage(
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                total_tokens=total_tokens
            ),
            duration_ms=duration_ms,
            start_time=self.call_start_datetime or "",
            end_time=end_datetime
        )
        
        # Log to structured logger
        log_llm_call(self.current_log)
        
        self.logger.info(
            f"[LLM_END] type={self.call_type} model={self.model_name} "
            f"duration_ms={duration_ms:.2f} tokens={{in={self.input_tokens}, out={self.output_tokens}, total={total_tokens}}}"
        )
        
        # Log response at DEBUG level
        for i, resp in enumerate(self.responses):
            self.logger.debug(f"[LLM_RESPONSE_{i}] {resp[:1000]}{'...' if len(resp) > 1000 else ''}")
        
        # Log thinking content if present
        if self.thinking_content:
            for i, thinking in enumerate(self.thinking_content):
                self.logger.debug(f"[LLM_THINKING_{i}] {thinking[:500]}{'...' if len(thinking) > 500 else ''}")
    
    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM errors."""
        end_time = time()
        end_datetime = datetime.now(timezone.utc).isoformat()
        duration_ms = (end_time - self.call_start_time) * 1000 if self.call_start_time else 0
        
        import traceback
        error_traceback = traceback.format_exc()
        
        self.current_log = LLMCallLog(
            call_type=self.call_type,
            model_name=self.model_name,
            provider=self.provider,
            prompt="\n---\n".join(self.prompts),
            error=str(error),
            error_traceback=error_traceback,
            duration_ms=duration_ms,
            start_time=self.call_start_datetime or "",
            end_time=end_datetime
        )
        
        # Log to structured logger
        log_llm_call(self.current_log)
        
        self.logger.error(
            f"[LLM_ERROR] type={self.call_type} model={self.model_name} "
            f"error={str(error)} duration_ms={duration_ms:.2f}"
        )
        self.logger.debug(f"[LLM_ERROR_TRACEBACK] {error_traceback}")
    
    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when chain starts running."""
        chain_name = serialized.get("name", "unknown")
        self.logger.info(f"[CHAIN_START] name={chain_name} input_keys={list(inputs.keys())}")
        
        # Log inputs at DEBUG level (be careful with large inputs)
        for key, value in inputs.items():
            value_str = str(value)
            self.logger.debug(
                f"[CHAIN_INPUT] {key}={value_str[:500]}{'...' if len(value_str) > 500 else ''}"
            )
    
    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when chain ends running."""
        self.logger.info(f"[CHAIN_END] output_keys={list(outputs.keys())}")
        
        # Log outputs at DEBUG level
        for key, value in outputs.items():
            value_str = str(value)
            self.logger.debug(
                f"[CHAIN_OUTPUT] {key}={value_str[:500]}{'...' if len(value_str) > 500 else ''}"
            )
    
    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when chain errors."""
        import traceback
        error_traceback = traceback.format_exc()
        
        self.logger.error(f"[CHAIN_ERROR] error={str(error)}")
        self.logger.debug(f"[CHAIN_ERROR_TRACEBACK] {error_traceback}")
    
    def get_llm_call_log(self) -> Optional[LLMCallLog]:
        """Get the LLM call log from the last call."""
        return self.current_log


def create_llm_callback(
    call_type: str,
    model_name: str = "",
    provider: str = ""
) -> DetailedLLMCallback:
    """
    Create a new DetailedLLMCallback instance.
    
    Args:
        call_type: Type of call (cypher_generation, qa_response, etc.)
        model_name: Name of the model being used
        provider: LLM provider name
        
    Returns:
        DetailedLLMCallback instance
    """
    return DetailedLLMCallback(
        call_type=call_type,
        model_name=model_name,
        provider=provider
    )
