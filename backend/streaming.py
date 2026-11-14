"""Live agent progress, streamed to the UI as NDJSON (one JSON event per line).

Event shapes (shared by the search agent and the outreach agent):

    {"type": "step",   "step": "scan", "status": "running", "title": "Scanning listings", "detail": "..."}
    {"type": "step",   "step": "scan", "status": "done" | "skipped" | "failed", "detail": "..."}
    {"type": "log",    "step": "scan", "text": "Found 24 listings", "kind": "info" | "ok" | "warn"}
    {"type": "agent",  "step": "inspect", "agent": "listing-1", "label": "Agent 1",
                       "status": "running" | "done" | "failed", "detail": "...", "hub": "Orchestrator"}
    {"type": "result", ...payload}
    {"type": "error",  "detail": "..."}

The frontend reduces these into its step list (see frontend/src/lib/trace.ts).
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, AsyncIterator, Callable, Literal, Optional

Emit = Callable[[dict[str, Any]], None]
LogKind = Literal["info", "ok", "warn"]
StepStatus = Literal["running", "done", "skipped", "failed"]

NDJSON_MEDIA_TYPE = "application/x-ndjson"


class Cancelled(Exception):
    """Raised inside a pipeline when the client that is watching it disconnected."""


class StepReporter:
    """Small helper that turns pipeline progress into stream events. No-op without `emit`."""

    def __init__(self, emit: Optional[Emit] = None) -> None:
        self._emit = emit

    def __bool__(self) -> bool:
        return self._emit is not None

    def event(self, event: dict[str, Any]) -> None:
        if self._emit:
            self._emit(event)

    def start(self, step: str, title: str, detail: Optional[str] = None) -> None:
        self.event({"type": "step", "step": step, "status": "running", "title": title, "detail": detail})

    def log(self, step: str, text: str, kind: LogKind = "info") -> None:
        self.event({"type": "log", "step": step, "text": text, "kind": kind})

    def done(self, step: str, detail: Optional[str] = None, status: StepStatus = "done") -> None:
        self.event({"type": "step", "step": step, "status": status, "detail": detail})

    def agent(
        self,
        step: str,
        agent: str,
        label: str,
        status: StepStatus,
        detail: Optional[str] = None,
        hub: Optional[str] = None,
    ) -> None:
        """A collaborating sub-agent inside a step (drawn as a node linked to the step's hub)."""
        event: dict[str, Any] = {
            "type": "agent", "step": step, "agent": agent, "label": label,
            "status": status, "detail": detail,
        }
        if hub:
            event["hub"] = hub
        self.event(event)


def ndjson_line(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False, default=str) + "\n"


async def stream_sync_pipeline(
    run: Callable[[Emit], Any],
    to_result: Callable[[Any], dict[str, Any]],
) -> AsyncIterator[str]:
    """Runs a blocking pipeline in a worker thread and yields its progress events as NDJSON.

    `run(emit)` may call `emit` from any thread. Its return value is turned into the final
    `result` event by `to_result`. If the client disconnects, the next `emit` call raises
    `Cancelled` inside the pipeline so it stops spending API credits.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue()
    cancelled = threading.Event()

    def emit(event: dict[str, Any]) -> None:
        if cancelled.is_set():
            raise Cancelled()
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def worker() -> None:
        try:
            result = run(emit)
            final = {"type": "result", **to_result(result)}
        except Cancelled:
            final = None
        except Exception as exc:  # Reported to the client, which falls back to demo data.
            final = {"type": "error", "detail": str(exc) or exc.__class__.__name__}
        if final is not None:
            loop.call_soon_threadsafe(queue.put_nowait, final)
        loop.call_soon_threadsafe(queue.put_nowait, None)

    thread = threading.Thread(target=worker, name="agent-pipeline", daemon=True)
    thread.start()
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield ndjson_line(event)
    finally:
        cancelled.set()


async def stream_async_events(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    """NDJSON-encodes an async event generator, turning an unexpected crash into an error event."""
    try:
        async for event in events:
            yield ndjson_line(event)
    except Exception as exc:
        yield ndjson_line({"type": "error", "detail": str(exc) or exc.__class__.__name__})
