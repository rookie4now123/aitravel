import logging
import re

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
    return any(keyword in text for keyword in keywords)


def _score_chunk_for_rerank(
    query: str,
    chunk: dict[str, str],
    destination: str | None = None,
) -> int:
    """Rate the relevance of a retrieved chunk to the query based on keyword matches and heuristics."""
    title = chunk.get("title", "")
    text = chunk.get("text", "")
    source = chunk.get("source", "")
    combined_text = f"{title}\n{text}"
    reasons: list[str] = []

    score = 0
    for keyword in _extract_query_keywords(query):
        if keyword in title:
            score += 3
            reasons.append(f"title+3:{keyword}")
        if keyword in text:
            score += 1
            reasons.append(f"text+1:{keyword}")

    # Initial chunks at the beginning of documents are often low-information noise.
    if title == "Initial Chunk":
        score -= 8
        reasons.append("noise-8:Initial Chunk")

    # Itinerary clips are good for "attractions/itinerary/recommendation" type of queries.
    if "Itinerary" in title and "Itinerary Reference" not in title:
        score += 4
        reasons.append("domain+4:Itinerary Title")

    # Classic Itinerary Reference chunks are comprehensive and often dominate top results, so they are demoted for non-itinerary queries.
    if "Itinerary Reference" in title:
        score -= 4
        reasons.append("domain-4:Itinerary Reference downgrade weight")

    # "Destination introduction" chunks are often too generic and not the best candidates for specific queries (food, family-friendly, etc.).
    if "Destination introduction" in title:
        score -= 2
        reasons.append("domain-2:Destination introduction downgrade weight")

    # "Cuisine/Budget" chunks are often not the best candidates for "sunset/photo relaxed" type of queries.
    if _contains_any(title, ["Cuisine", "Budget"]) and not _contains_any(
        combined_text,
        ["Sunset", "Dusk", "Photo", "Video", "Good Photo", "Vestula", "Boltic", "Low Rythems"],
    ):
        score -= 3
        reasons.append("domain-3:Cuisine/Budget weakly relevant")

    # Destination mismatch downgrade: chunks from a different destination are downgraded when the query specifies a particular destination.
    if destination:
        chunk_lower = f"{source} {title} {text}".lower()
        if destination.lower() not in chunk_lower:
            score -= 5
            reasons.append(f"dest-5:non-{destination} chunk")

    chunk["rerank_reasons"] = reasons
    return score


def rerank_guide_chunks(
    query: str,
    matched_chunks: list[dict[str, str]],
    top_k: int,
    destination: str | None = None,
) -> list[dict[str, str]]:
    """Reorder the retrieved candidates with a lightweight heuristic and cut to final top_k."""
    scored_chunks: list[tuple[int, int, dict[str, str]]] = []
    for index, chunk in enumerate(matched_chunks):
        enriched_chunk = dict(chunk)
        score = _score_chunk_for_rerank(query, enriched_chunk, destination=destination)
        enriched_chunk["rerank_score"] = score
        scored_chunks.append((score, -index, enriched_chunk))

    scored_chunks.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [chunk for _, _, chunk in scored_chunks[:top_k]]


def retrieve_travel_guide_chunks(
    query: str, top_k: int = 3, destination: str | None = None
) -> list[dict[str, str]]:
    """Return the original guide chunks with lightweight reranking for debugging and upper-layer reuse."""
    candidate_k = max(top_k * 2, 6)
    matched_chunks = search_guide_chunks(query=query, top_k=candidate_k)
    return rerank_guide_chunks(
        query=query, matched_chunks=matched_chunks, top_k=top_k, destination=destination
    )


def retrieve_travel_guide(query: str, top_k: int = 3) -> list[str]:
    """Return the most relevant guide chunks for assembling context."""
    cache_key = f"rag:guide:{_normalize_cache_text(query)}:{top_k}"
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("rag cache hit: query=%s top_k=%s", query, top_k)
        return [str(item) for item in cached_value]
    logger.info("rag cache miss: query=%s top_k=%s", query, top_k)

    matched_chunks = retrieve_travel_guide_chunks(query=query, top_k=top_k)

    results: list[str] = []
    for chunk in matched_chunks:
        results.append(
            f"[Source: {chunk['source']} | Title: {chunk['title']}]\n{chunk['text']}"
        )

    set_cached_json(cache_key, results, expire_seconds=REDIS_RAG_TTL_SECONDS)
    return results
