from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Trip Planner Demo Backend",
        description="MVP backend for the intelligent travel assistant.",
        version="0.1.0",
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
