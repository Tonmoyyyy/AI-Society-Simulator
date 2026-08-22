import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import auth as auth_routes
from app.api.v1 import citizens as citizen_routes
from app.api.v1 import dashboard as dashboard_routes
from app.api.v1 import government as government_routes
from app.api.v1 import shop as shop_routes
from app.api.v1 import simulation as simulation_routes
from app.api.v1 import social as social_routes
from app.api.v1 import wallet as wallet_routes
from app.api.v1 import world as world_routes
from app.core.config import settings
from app.core.error_handlers import register_error_handlers
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.simulation.seed_shops import ensure_seed_shops
from app.services.government_service import ensure_government
from app.services.world_generation_service import ensure_world_generated
from app.services.world_service import ensure_seed_world
from app.websocket.connection_manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await run_in_threadpool(Base.metadata.create_all, bind=engine)
    except Exception as exc:
        print(f"[startup] Skipping auto-create tables: {exc}")

    def _seed():
        db = SessionLocal()
        try:
            ensure_seed_shops(db)
        finally:
            db.close()

    try:
        await run_in_threadpool(_seed)
    except Exception as exc:
        print(f"[startup] Skipping shop seed: {exc}")

    def _seed_world():
        db = SessionLocal()
        try:
            ensure_seed_world(db)
        finally:
            db.close()

    try:
        await run_in_threadpool(_seed_world)
    except Exception as exc:
        print(f"[startup] Skipping world seed: {exc}")

    def _generate_world():
        db = SessionLocal()
        try:
            ensure_world_generated(db)
        finally:
            db.close()

    try:
        await run_in_threadpool(_generate_world)
    except Exception as exc:
        print(f"[startup] Skipping world generation: {exc}")

    def _seed_government():
        db = SessionLocal()
        try:
            ensure_government(db)
        finally:
            db.close()

    try:
        await run_in_threadpool(_seed_government)
    except Exception as exc:
        print(f"[startup] Skipping government seed: {exc}")

    manager.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

# CORS Middleware (Must be applied first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handler (Fixes CORS blocking on 500 Internal Server Errors)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"\n[BACKEND ERROR DETECTED]: {exc}\n")
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"error": {"code": 500, "message": str(exc)}},
        headers={"Access-Control-Allow-Origin": "*"}
    )

register_error_handlers(app)

app.include_router(auth_routes.router)
app.include_router(citizen_routes.router)
app.include_router(simulation_routes.router)
app.include_router(social_routes.router)
app.include_router(wallet_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(shop_routes.router)
app.include_router(world_routes.router)
app.include_router(government_routes.router)


@app.websocket("/ws/feed")
async def feed_websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}