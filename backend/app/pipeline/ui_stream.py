# ui_stream.py: the live console stream (K11). A broadcaster keeps each tenant's recent ui.events and hands them
# to listeners; an SSE app streams them, with a "delayed" notice when the recorder is behind (reference doc section 8).
# Used by: orchestrate.py (broadcaster consumer), the API in step 9 (create_stream_app), tests. Uses: observe.py.
import json
import queue
from collections import deque

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.pipeline.observe import read_flag

# Config
RECENT_PER_TENANT = 100  # a reconnecting console catches up from these
HEARTBEAT_SECONDS = 15


class Broadcaster:
    """A class because each tenant's recent events and listener queues are state shared by publish and stream."""

    def __init__(self):
        self.recent: dict[str, deque] = {}
        self.listeners: dict[str, list[queue.Queue]] = {}

    def publish(self, envelope) -> None:
        """Consumer of ui.events: remember the event and hand it to every listener of its tenant."""
        tenant = envelope.payload["tenant_id"]
        self.recent.setdefault(tenant, deque(maxlen=RECENT_PER_TENANT)).append(envelope.payload)
        for listener in self.listeners.get(tenant, []):
            listener.put(envelope.payload)

    def listen(self, tenant_id: str) -> tuple[list[dict], queue.Queue]:
        """Recent events to catch up on, and a queue for what comes next."""
        listener: queue.Queue = queue.Queue()
        self.listeners.setdefault(tenant_id, []).append(listener)
        return list(self.recent.get(tenant_id, [])), listener


def subscribe_broadcaster(bus, broadcaster: Broadcaster) -> None:
    bus.subscribe("ui.events", "sse_gateway", "S10", broadcaster.publish)


def sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


def stream_events(broadcaster: Broadcaster, tenant_id: str, limit: int | None):
    """Catch-up events, then live ones, with heartbeats. limit stops the stream (for tests and short polls)."""
    recent, listener = broadcaster.listen(tenant_id)
    if read_flag("recorder_delayed"):
        yield sse("delayed", {"reason": "the recorder is behind; updates will arrive late"})
    sent = 0
    for event in recent:
        yield sse(event["type"], event)
        sent += 1
        if limit is not None and sent >= limit:
            return
    while limit is None or sent < limit:
        try:
            event = listener.get(timeout=HEARTBEAT_SECONDS)
        except queue.Empty:
            yield ": heartbeat\n\n"
            continue
        yield sse(event["type"], event)
        sent += 1


def create_stream_app(broadcaster: Broadcaster) -> FastAPI:
    """GET /api/stream?tenant_id=... as Server-Sent Events. Step 9 mounts this into the main API, behind sign-in."""
    app = FastAPI(title="finebrain stream")

    @app.get("/api/stream")
    def stream(tenant_id: str, limit: int | None = None) -> StreamingResponse:
        return StreamingResponse(stream_events(broadcaster, tenant_id, limit), media_type="text/event-stream")

    return app
