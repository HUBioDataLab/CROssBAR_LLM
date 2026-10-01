"""Server-sent-event responses for orchestrated requests.

A multi-agent answer can take minutes, and the UI wants to show which agents
are working meanwhile. Each event is `event: <name>` plus a JSON `data:` line.
The stream ends with exactly one `result` (the same body the JSON endpoint
returns) or one `error` (`status_code` and `detail`, as an HTTP error would
carry).
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from crossbar_llm.agent_tools.logging_config import get_logger
from crossbar_llm.api.services.orchestration_events import EventSink

logger = get_logger(__name__)

RESULT_EVENT = "result"
ERROR_EVENT = "error"
UNEXPECTED_ERROR = "The request failed unexpectedly. See the server logs for details."

_DONE = object()


def format_event(event: str, data: Any) -> str:
    payload = json.dumps(data, default=str, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def stream_orchestration(
    run: Callable[[EventSink], Awaitable[BaseModel]],
    *,
    keepalive_seconds: float,
) -> StreamingResponse:
    """Stream `run`'s progress events, then its result.

    If the client disconnects, Starlette cancels the body generator, which
    cancels `run` — and with it every agent still working on the answer.
    """
    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def emit(event: str, data: dict[str, Any]) -> None:
        await queue.put((event, data))

    async def produce() -> None:
        try:
            response = await run(emit)
            await queue.put((RESULT_EVENT, response.model_dump(mode="json")))
        except HTTPException as error:
            await queue.put(
                (ERROR_EVENT, {"status_code": error.status_code, "detail": error.detail})
            )
        except Exception as error:
            # The response has already started, so this cannot become a 500;
            # it is logged in full and reported without upstream detail.
            logger.error(
                "Streamed orchestration failed",
                event_type="orchestration_stream_failed",
                component="streaming.stream_orchestration",
                error_type=type(error).__name__,
                error=str(error),
                exc_info=error,
            )
            await queue.put((ERROR_EVENT, {"status_code": 500, "detail": UNEXPECTED_ERROR}))
        finally:
            await queue.put(_DONE)

    async def body() -> AsyncIterator[str]:
        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=keepalive_seconds)
                except TimeoutError:
                    # An SSE comment: ignored by clients, but keeps proxies from
                    # closing a connection that is waiting on a slow agent.
                    yield ": keep-alive\n\n"
                    continue
                if item is _DONE:
                    break
                yield format_event(*item)
        finally:
            producer.cancel()
            with suppress(asyncio.CancelledError):
                await producer

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
