from app.rag.retriever import retrieve_travel_guide


# rag_tool.py is responsible for building the retrieval query based on travel planning semantics.

def _append_unique(parts: list[str], value: str) -> None:
    normalized = value.strip()
    if not normalized:
        return
    if normalized not in parts:
        parts.append(normalized)


def _extract_note_keywords(special_notes: str | None, destination: str | None = None) -> list[str]:
    """Extract keywords from user notes, which is more suitable for retrieval than the whole sentence."""
    if not special_notes:
        return []

    keywords: list[str] = []
    note_lower = special_notes.strip().lower()
    dest_lower = (destination or "").strip().lower()

    # Format: (trigger_words, destination_filter, output_keywords)
    rule_keywords = [
        (("sunset", "evening"), "Barcelona", ["sunset", "evening", "beach", "Barceloneta"]),
        (("sunrise", "morning"), "Paris", ["sunrise", "Seine", "Eiffel Tower"]),
        (("photography", "photos", "shooting"), None, ["photography", "city view", "landmarks"]),
        (("food", "local food", "eat"), None, ["food", "local cuisine"]),
        (("relax", "slow pace", "chill"), None, ["relax", "slow pace", "café culture"]),
        (("sleep in", "no early wake up"), None, ["relax", "slow pace"]),
        (("old town",), "Krakow", ["old town", "Wawel Castle", "Kazimierz"]),
        (("old town",), "Florence", ["old town", "Duomo", "Piazza della Signoria"]),
        (("old town",), "Barcelona", ["old town", "Gothic Quarter"]),
        (("cycling",), "Milan", ["cycling", "city streets", "parks"]),
        (("cycling",), "Barcelona", ["cycling", "coastal road"]),
        (("art", "museum"), "Paris", ["art", "Louvre", "museum"]),
        (("art", "museum"), "Florence", ["art", "Uffizi Gallery", "Renaissance"]),
        (("architecture",), "Barcelona", ["architecture", "Sagrada Familia", "Gaudi"]),
        (("architecture",), "Madrid", ["architecture", "Royal Palace"]),
        (("nightlife",), "Madrid", ["nightlife", "bars", "city center"]),
        (("shopping",), "Milan", ["shopping", "fashion district"]),
    ]

    for triggers, required_dest, values in rule_keywords:
        if required_dest and dest_lower and required_dest.lower() not in dest_lower:
            continue
        if any(trigger.lower() in note_lower for trigger in triggers):
            for value in values:
                _append_unique(keywords, value)

    return keywords


def build_destination_query(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
) -> str:
    """Build a retrieval query based on destination, preferences, pace, and special notes."""
    parts: list[str] = [destination]

    if preferences:
        for preference in preferences:
            _append_unique(parts, preference)

    if pace:
        _append_unique(parts, pace)

    for keyword in _extract_note_keywords(special_notes, destination=destination):
        _append_unique(parts, keyword)

    for stable_term in ["Scenic Spots", "Itinerary", "Plan", "Recommendation"]:
        _append_unique(parts, stable_term)

    return " ".join(part for part in parts if part).strip()


def _build_destination_query(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
) -> str:
    """Compatible with old calls, internally redirect to the public query construction function."""
    return build_destination_query(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
    )


def get_destination_guide_context(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
    top_k: int = 5,
) -> list[str]:
    """Return relevant segments from local guides based on destination and preferences."""
    query = build_destination_query(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
    )
    return retrieve_travel_guide(query=query, top_k=top_k, destination=destination)