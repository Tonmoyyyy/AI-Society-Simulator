import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.error_handlers import register_error_handlers
from app.api.v1 import auth as auth_routes
from app.api.v1 import citizens as citizen_routes
from app.api.v1 import simulation as simulation_routes
from app.api.v1 import social as social_routes
from app.api.v1 import wallet as wallet_routes
from app.websocket.connection_manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lets the tick scheduler (a background thread) safely broadcast onto
    # this event loop — see websocket/connection_manager.py.
    manager.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

register_error_handlers(app)

app.include_router(auth_routes.router)
app.include_router(citizen_routes.router)
app.include_router(simulation_routes.router)
app.include_router(social_routes.router)
app.include_router(wallet_routes.router)


@app.websocket("/ws/feed")
async def feed_websocket(websocket: WebSocket):
    """Realtime feed: pushes {"type": "new_post" | "new_comment", ...}
    events as they happen (from ticks or the API). Clients don't need to
    send anything — this just keeps the connection open."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/health", tags=["health"])
def health_check():
    """Basic liveness check — also useful to confirm the app boots at all."""
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}
