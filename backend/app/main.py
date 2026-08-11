import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool  # <-- table creation ব্লক না করার জন্য
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth as auth_routes
from app.api.v1 import citizens as citizen_routes
from app.api.v1 import dashboard as dashboard_routes
from app.api.v1 import shop as shop_routes
from app.api.v1 import simulation as simulation_routes
from app.api.v1 import social as social_routes
from app.api.v1 import wallet as wallet_routes  # <-- আগে বাদ পড়ে গিয়েছিল
from app.core.config import settings
from app.core.error_handlers import register_error_handlers
from app.db.base import Base  # ডাটাবেজ মডেলের Base ইমপোর্ট
from app.db.session import engine, SessionLocal  # SQLAlchemy engine ইমপোর্ট
from app.simulation.seed_shops import ensure_seed_shops
from app.websocket.connection_manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ১. টেবিল ক্রিয়েশনকে থ্রেডপুলে রান করা হচ্ছে যেন Event Loop ব্লক না হয়
    #    (safety-net — আসল schema source of truth এখনও Alembic migrations)
    # try/except: this talks to the real MySQL engine directly, which the
    # test suite's SQLite override does NOT patch (only get_db is patched).
    # Without this guard, pytest — and any real startup before MySQL is
    # up — crashes the whole app here instead of just skipping the
    # convenience step.
    try:
        await run_in_threadpool(Base.metadata.create_all, bind=engine)
    except Exception as exc:
        print(f"[startup] Skipping auto-create tables (DB not reachable yet?): {exc}")

    # Seed starter shops/products so the marketplace isn't empty out of the
    # box — idempotent (no-op if shops already exist), same resilience
    # pattern as create_all above.
    def _seed():
        db = SessionLocal()
        try:
            ensure_seed_shops(db)
        finally:
            db.close()

    try:
        await run_in_threadpool(_seed)
    except Exception as exc:
        print(f"[startup] Skipping shop seed (DB not reachable yet?): {exc}")

    # ২. Websocket event loop bind
    manager.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

# v0.1 frontend is static HTML/JS served from its own dev port (see
# frontend/README.md) — no cookies/credentials involved (JWT goes in a
# header, not a cookie), so a permissive local-dev CORS policy is fine.
# Tighten this to a specific origin before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(auth_routes.router)
app.include_router(citizen_routes.router)
app.include_router(simulation_routes.router)
app.include_router(social_routes.router)
app.include_router(wallet_routes.router)  # <-- আগে বাদ পড়ে গিয়েছিল
app.include_router(dashboard_routes.router)
app.include_router(shop_routes.router)


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
