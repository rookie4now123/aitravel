from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import api_router
from app.rag.sqlite_store import ingest_guide_chunks_to_sqlite
from app.services.cache_service import close_redis_client
from app.services.storage_service import init_db


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize application resources on startup and clean up on shutdown."""
    init_db()
    try:
        chunk_count = ingest_guide_chunks_to_sqlite()
        logger.info("Indexed %d RAG guide chunks into SQLite FTS.", chunk_count)
    except Exception as exc:
        logger.warning("Failed to ingest RAG guide chunks on startup: %s", exc)
    try:
        yield
    finally:
        close_redis_client()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Trip Planner Demo Backend",
        description="MVP backend for the intelligent travel assistant.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def read_root() -> dict[str, str]:
        """Root endpoint used to confirm the backend is running."""
        return {"message": "Trip Planner Demo backend is running."}

    @app.get("/health")
    def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    # Preserve existing frontend/script URLs while also exposing versioned APIs.
    app.include_router(api_router)
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()