"""
Single-instance WebSocket broadcast for the live feed (see SDD — Redis
pub/sub deferred; one process is enough at v0.1 scale).

Both FastAPI's sync `def` route handlers and the APScheduler tick job run
outside the main event loop (in worker threads), so neither can `await`
directly. `broadcast_threadsafe` covers both cases uniformly via
`asyncio.run_coroutine_threadsafe`.
"""

import asyncio
import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once at app startup so background threads can safely
        schedule broadcasts onto the request-serving event loop."""
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for connection in self._connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)

    def broadcast_threadsafe(self, message: dict[str, Any]) -> None:
        """Safe to call from any sync context (API route handlers, the
        tick scheduler thread). No-op if no loop is bound yet or no
        clients are connected."""
        if self._loop is None or not self._connections:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)


manager = ConnectionManager()
