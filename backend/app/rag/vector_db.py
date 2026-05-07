"""Backward-compatible RAG store imports.

The RAG store now uses SQLite FTS. New code should import from
``app.rag.sqlite_store``.
"""

from app.rag.sqlite_store import (  # noqa: F401
    ingest_guide_chunks_to_sqlite,
    load_guide_chunks,
    search_guide_chunks,
)
