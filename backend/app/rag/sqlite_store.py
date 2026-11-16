from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from hashlib import md5

from app.core.config import BACKEND_DIR, RAG_SQLITE_DB_PATH


DATA_DIR = BACKEND_DIR / "data"


def _split_markdown_into_chunks(markdown_text: str, source_name: str) -> list[dict[str, str]]:
    """Split Markdown by H2/H3 headers into retrievable chunks."""
    chunks: list[dict[str, str]] = []
    current_title = "Document Start"
    current_lines: list[str] = []

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            if current_lines:
                chunks.append(
                    {
                        "title": current_title,
                        "text": "\n".join(current_lines).strip(),
                        "source": source_name,
                    }
                )
                current_lines = []
            current_title = stripped.lstrip("#").strip()
        elif stripped:
            current_lines.append(stripped)

    if current_lines:
        chunks.append(
            {
                "title": current_title,
                "text": "\n".join(current_lines).strip(),
                "source": source_name,
            }
        )

    return chunks


def _build_chunk_id(source: str, title: str, text: str) -> str:
    """Generate a stable chunk ID based on source, title, and text."""
    digest = md5(f"{source}|{title}|{text}".encode("utf-8")).hexdigest()
    return f"{source}_{digest}"


def _build_document_text(chunk: dict[str, str]) -> str:
    """Compose title and text into a single string for retrieval."""
    return f"{chunk['title']}\n{chunk['text']}"


def load_guide_chunks() -> list[dict[str, str]]:
    """Read the guide files under backend/data and split them into retrievable chunks."""
    if not DATA_DIR.exists():
        return []

    chunks: list[dict[str, str]] = []
    for guide_file in sorted(DATA_DIR.glob("*.md*")):
        text = guide_file.read_text(encoding="utf-8")
        raw_chunks = _split_markdown_into_chunks(text, guide_file.name)
        for chunk in raw_chunks:
            chunks.append(
                {
                    "id": _build_chunk_id(chunk["source"], chunk["title"], chunk["text"]),
                    "title": chunk["title"],
                    "text": chunk["text"],
                    "source": chunk["source"],
                }
            )
    return chunks


def _extract_keywords(query: str) -> list[str]:
    """Split the query into simple keywords for SQLite FTS and fallback matching."""
    raw_keywords = re.split(r"[\s,，。；;、]+", query)
    return [keyword.strip() for keyword in raw_keywords if keyword.strip()]


def _score_chunk(query: str, chunk_text: str) -> int:
    """Score a chunk based on case-insensitive keyword occurrences."""
    keywords = _extract_keywords(query)
    chunk_lower = chunk_text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in chunk_lower)


def _search_guide_chunks_by_keywords(query: str, top_k: int = 3) -> list[dict[str, str]]:
    """Fallback method: Use keyword matching to search local guide chunks."""
    scored_chunks: list[tuple[int, dict[str, str]]] = []
    for chunk in load_guide_chunks():
        score = _score_chunk(query, _build_document_text(chunk))
        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored_chunks[:top_k]]


def _connect() -> sqlite3.Connection:
    RAG_SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(RAG_SQLITE_DB_PATH, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA busy_timeout=30000;")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS guide_chunks (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            document_text TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS guide_chunks_fts
        USING fts5(
            id UNINDEXED,
            source UNINDEXED,
            title,
            text,
            tokenize = 'unicode61'
        )
        """
    )
    connection.commit()


def ingest_guide_chunks_to_sqlite() -> int:
    """Write the local guide chunks into SQLite FTS index."""
    chunks = load_guide_chunks()

    with closing(_connect()) as connection:
        _ensure_schema(connection)
        with connection:
            connection.execute("DELETE FROM guide_chunks")
            connection.execute("DELETE FROM guide_chunks_fts")

            for chunk in chunks:
                document_text = _build_document_text(chunk)
                connection.execute(
                    """
                    INSERT INTO guide_chunks (id, source, title, text, document_text)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        chunk["id"],
                        chunk["source"],
                        chunk["title"],
                        chunk["text"],
                        document_text,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO guide_chunks_fts (id, source, title, text)
                    VALUES (?, ?, ?, ?)
                    """,
                    (chunk["id"], chunk["source"], chunk["title"], chunk["text"]),
                )

    return len(chunks)


def _build_fts_query(query: str) -> str:
    terms = _extract_keywords(query)
    quoted_terms = [f'"{term.replace(chr(34), chr(34) + chr(34))}"' for term in terms]
    return " OR ".join(quoted_terms)


def _search_guide_chunks_by_sqlite(query: str, top_k: int = 3) -> list[dict[str, str]]:
    """Search the ingested guide chunks using SQLite FTS first."""
    fts_query = _build_fts_query(query)
    if not fts_query or not RAG_SQLITE_DB_PATH.exists():
        return []

    try:
        with closing(_connect()) as connection:
            _ensure_schema(connection)
            row = connection.execute("SELECT COUNT(*) AS count FROM guide_chunks").fetchone()
            if row is None or row["count"] == 0:
                return []

            rows = connection.execute(
                """
                SELECT
                    c.source,
                    c.title,
                    c.text,
                    bm25(guide_chunks_fts) AS rank
                FROM guide_chunks_fts
                JOIN guide_chunks AS c ON c.id = guide_chunks_fts.id
                WHERE guide_chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, top_k),
            ).fetchall()
    except sqlite3.Error:
        return []

    return [
        {
            "source": str(row["source"]),
            "title": str(row["title"]),
            "text": str(row["text"]),
        }
        for row in rows
    ]


def search_guide_chunks(query: str, top_k: int = 3) -> list[dict[str, str]]:
    """
    Search the most relevant top_k results from local guide chunks.

    Try SQLite FTS first; if the index is not ready, fallback to direct keyword matching.
    """
    sqlite_results = _search_guide_chunks_by_sqlite(query=query, top_k=top_k)
    if sqlite_results:
        return sqlite_results
    return _search_guide_chunks_by_keywords(query=query, top_k=top_k)