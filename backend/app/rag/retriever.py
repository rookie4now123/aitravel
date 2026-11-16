import logging
import re
from typing import Any

from app.core.config import REDIS_RAG_TTL_SECONDS
from app.rag.sqlite_store import search_guide_chunks
from app.services.cache_service import get_cached_json, set_cached_json


logger = logging.getLogger(__name__)


def _normalize_cache_text(value: str) -> str:
    """Standardize the retrieval query to avoid duplicate keys caused by case and whitespace."""
    return " ".join(value.strip().lower().split())


def _extract_query_keywords(query: str) -> list[str]:
    """Extract keywords from the query for lightweight re-ranking."""
    raw_parts = re.split(r"[\s,，。；;、]+", query)
    return [part.strip() for part in raw_parts if part.strip()]


def _contains_any(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in keywords)


def _score_chunk_for_rerank(
    query: str,
    chunk: dict[str, Any],
    destination: str | None = None,
) -> int:
    """Rate the relevance of a retrieved chunk to the query based on keyword matches and heuristics."""
    title = str(chunk.get("title", ""))
    text = str(chunk.get("text", ""))
    source = str(chunk.get("source", ""))
    title_lower = title.lower()
    text_lower = text.lower()
    combined_text = f"{title}\n{text}"
    reasons: list[str] = []

    score = 0
    for keyword in _extract_query_keywords(query):
        kw_lower = keyword.lower()
        if kw_lower in title_lower:
            score += 3
            reasons.append(f"title+3:{keyword}")
        if kw_lower in text_lower:
            score += 1
            reasons.append(f"text+1:{keyword}")

    # Initial chunks at the beginning of documents are often low-information noise.
    if title_lower in ("initial chunk", "document start"):
        score -= 8
        reasons.append("noise-8:Document Start")

    # Itinerary clips are good for "attractions/itinerary/recommendation" queries.
    if "itinerary" in title_lower and "itinerary reference" not in title_lower:
        score += 4
        reasons.append("domain+4:Itinerary Title")

    # Classic Itinerary Reference chunks often dominate top results, so demote slightly.
    if "itinerary reference" in title_lower:
        score -= 4
        reasons.append("domain-4:Itinerary Reference downgrade weight")

    # Generic introduction chunks are less useful for specific queries.
    if "destination introduction" in title_lower:
        score -= 2
        reasons.append("domain-2:Destination introduction downgrade weight")

    # Cuisine/Budget chunks are weakly relevant to sunset/photo/relaxed scenic queries.
    if _contains_any(title, ["cuisine", "budget"]) and not _contains_any(
        combined_text,
        ["sunset", "dusk", "photo", "photography", "vistula", "baltic", "slow", "relax"],
    ):
        score -= 3
        reasons.append("domain-3:Cuisine/Budget weakly relevant")

    # Destination mismatch downgrade
    if destination:
        chunk_lower = f"{source} {title} {text}".lower()
        if destination.strip().lower() not in chunk_lower:
            score -= 5
            reasons.append(f"dest-5:non-{destination} chunk")

    chunk["rerank_reasons"] = reasons
    return score


def rerank_guide_chunks(
    query: str,
    matched_chunks: list[dict[str, Any]],
    top_k: int,
    destination: str | None = None,
) -> list[dict[str, Any]]:
    """Reorder the retrieved candidates with a lightweight heuristic and cut to final top_k."""
    scored_chunks: list[tuple[int, int, dict[str, Any]]] = []
    for index, chunk in enumerate(matched_chunks):
        enriched_chunk: dict[str, Any] = dict(chunk)
        score = _score_chunk_for_rerank(query, enriched_chunk, destination=destination)
        enriched_chunk["rerank_score"] = score
        scored_chunks.append((score, -index, enriched_chunk))

    scored_chunks.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [chunk for _, _, chunk in scored_chunks[:top_k]]


def retrieve_travel_guide_chunks(
    query: str, top_k: int = 3, destination: str | None = None
) -> list[dict[str, Any]]:
    """Return the original guide chunks with lightweight reranking."""
    candidate_k = max(top_k * 2, 6)
    matched_chunks = search_guide_chunks(query=query, top_k=candidate_k)
    return rerank_guide_chunks(
        query=query, matched_chunks=matched_chunks, top_k=top_k, destination=destination
    )


def retrieve_travel_guide(
    query: str, top_k: int = 3, destination: str | None = None
) -> list[str]:
    """Return the most relevant guide chunks for assembling context."""
    dest_key = _normalize_cache_text(destination or "")
    cache_key = f"rag:guide:{dest_key}:{_normalize_cache_text(query)}:{top_k}"
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("rag cache hit: destination=%s query=%s top_k=%s", destination, query, top_k)
        return [str(item) for item in cached_value]
    logger.info("rag cache miss: destination=%s query=%s top_k=%s", destination, query, top_k)

    matched_chunks = retrieve_travel_guide_chunks(
        query=query, top_k=top_k, destination=destination
    )

    results: list[str] = []
    for chunk in matched_chunks:
        results.append(
            f"[Source: {chunk['source']} | Title: {chunk['title']}]\n{chunk['text']}"
        )

    set_cached_json(cache_key, results, expire_seconds=REDIS_RAG_TTL_SECONDS)
    return results