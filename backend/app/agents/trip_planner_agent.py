from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.agents.tools.rag_tool import get_destination_guide_context
from app.core.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)
from app.schemas.trip import DayPlan, TripEditRequest, TripRequest


class PlannerDayDraft(BaseModel):
    """Structured draft for a single day returned by the LLM."""

    day_index: int = Field(..., ge=1)
    theme: str = Field(..., description="Short theme for the day, e.g., 'Relaxing Beach Day' or 'Cultural Exploration'.")
    spot_name: str = Field(..., description="Name of the main attraction for the day")
    spot_description: str = Field(..., description="Brief reason for recommending the attraction")
    meal_name: str = Field(..., description="Name of the meal or restaurant for the day")
    meal_notes: str = Field(..., description="Brief notes about the meal")
    daily_note: str = Field(..., description="A brief planning note for the day")


class PlannerDraft(BaseModel):
    """Structured trip draft consumed by trip_service.py."""

    summary: str = Field(..., description="Short overview of the entire trip")
    tips: list[str] = Field(default_factory=list, description="Travel tips")
    days: list[PlannerDayDraft] = Field(default_factory=list)


class DayEditDraft(BaseModel):
    """Structured draft for editing a single day returned by the LLM."""

    theme: str = Field(..., description="Edited theme for the day")
    spot_name: str = Field(..., description="Edited name of the main attraction for the day")
    spot_description: str = Field(..., description="Edited description of the attraction")
    meal_name: str = Field(..., description="Edited name of the meal or restaurant for the day")
    meal_notes: str = Field(..., description="Edited notes about the meal")
    daily_note: str = Field(..., description="Edited planning note for the day")


def _normalize_day_edit_payload(payload: dict) -> dict:
    """Support both flat and nested day edit payload formats."""
    if "spot_name" in payload and "meal_name" in payload and "daily_note" in payload:
        return payload

    normalized = dict(payload)

    spots = payload.get("spots")
    if isinstance(spots, list) and spots:
        first_spot = spots[0] or {}
        normalized.setdefault("spot_name", first_spot.get("name", ""))
        normalized.setdefault("spot_description", first_spot.get("description", ""))

    meals = payload.get("meals")
    if isinstance(meals, list) and meals:
        first_meal = meals[0] or {}
        normalized.setdefault("meal_name", first_meal.get("name", ""))
        normalized.setdefault("meal_notes", first_meal.get("notes", ""))

    notes = payload.get("notes")
    if isinstance(notes, list) and notes:
        normalized.setdefault("daily_note", notes[-1] or "")

    return normalized


def _extract_json_object(raw_text: str) -> str | None:
    """Fallback JSON extraction from raw model text."""
    text = raw_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    start_index = text.find("{")
    end_index = text.rfind("}")
    if start_index == -1 or end_index == -1 or end_index <= start_index:
        return None

    return text[start_index : end_index + 1]


def _extract_raw_text(response: object) -> str:
    raw_text = getattr(response, "content", "")
    if isinstance(raw_text, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in raw_text
        )
    return str(raw_text)


def collect_trip_context(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
    top_k: int = 5,
) -> list[str]:
    """Collect local guide segments needed for trip planning."""
    return get_destination_guide_context(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
        top_k=top_k,
    )


def _build_chat_llm():
    """Create ChatGoogleGenerativeAI instance."""
    if not LLM_API_KEY:
        return None

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        return None

    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        temperature=0.3,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL or None,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )


def generate_planner_draft(
    request: TripRequest,
    rag_contexts: list[str],
    day_count: int,
) -> PlannerDraft | None:
    """
    Generate structured trip draft using LangChain `.with_structured_output`.
    Falls back to manual JSON extraction if schema-constrained invocation fails,
    and returns None if model invocation is unavailable so trip_service can fall back.
    """
    llm = _build_chat_llm()
    if llm is None:
        return None

    guide_context = "\n\n".join(rag_contexts) if rag_contexts else "No local context"

    system_prompt = (
        "You are a travel planning assistant. "
        "Please generate a concise structured travel draft in Europe. "
        "Follow the user's destination, budget, pace, and local guide context. "
        "If the user explicitly states specific requests in the additional notes—such as wanting to see "
        "the sunset, not wanting to wake up early, preferring less spice, or taking photos—prioritize "
        "incorporating these requests into the specific attractions or daily plans for a particular day "
        "rather than only writing general tips."
    )

    human_prompt = f"""
Destination: {request.destination}
Start Date: {request.start_date.isoformat()}
End Date: {request.end_date.isoformat()}
Day Count: {day_count}
Travelers: {request.travelers}
Budget: {request.budget}
Preferences: {', '.join(request.preferences) if request.preferences else 'No special preferences'}
Pace: {request.pace or 'Moderate'}
Dietary Preferences: {', '.join(request.dietary_preferences) if request.dietary_preferences else 'None'}
Hotel Level: {request.hotel_level or 'Comfortable'}
Additional Notes: {request.special_notes or 'None'}

Local Guide Context:
{guide_context}

Requirements:
1. Output an overall summary.
2. Output the daily draft for {day_count} days.
3. One main attraction, one meal recommendation, and one daily note for each day.
4. Keep tips concise and practical.
5. day_index must be sequentially numbered from 1 to {day_count}.
6. Specific requests in Additional Notes (such as watching the sunset or sleeping in) must be reflected directly in the days section, not just in tips.
7. If the plan includes watching the sunset, the spot_name for that day should be a location suitable for watching the sunset and consistent with the daily_note.
8. Every day's arrangement should follow the requested pace, avoiding overcrowding or overly early departures when relaxed.
9. Dining recommendations should prioritize restaurants or dishes that appeared in the Local Guide Context.
"""

    messages = [
        ("system", system_prompt),
        ("human", human_prompt),
    ]

    print("[trip_planner_agent] Invoking LLM with structured output...")
    print(f"[trip_planner_agent] model = {LLM_MODEL}")
    print(f"[trip_planner_agent] base_url = {LLM_BASE_URL or '<DEFAULT>'}")

    result: PlannerDraft | None = None
    try:
        structured_llm = llm.with_structured_output(PlannerDraft)
        raw_result = structured_llm.invoke(messages)
        result = (
            raw_result
            if isinstance(raw_result, PlannerDraft)
            else PlannerDraft.model_validate(raw_result)
        )
    except Exception as exc:
        print(
            "[trip_planner_agent] Structured output invocation failed, trying raw JSON fallback: "
            f"{type(exc).__name__}: {exc}"
        )
        try:
            response = llm.invoke(messages)
            json_text = _extract_json_object(_extract_raw_text(response))
            if json_text is not None:
                result = PlannerDraft.model_validate(json.loads(json_text))
        except Exception as fallback_exc:
            print(
                f"[trip_planner_agent] Fallback LLM invocation failed: {type(fallback_exc).__name__}: {fallback_exc}"
            )
            return None

    if result is None:
        return None

    if len(result.days) != day_count:
        print(
            "[trip_planner_agent] Structured result day count mismatch, "
            f"expected={day_count}, actual={len(result.days)}"
        )
        return None

    return result


def generate_day_edit_draft(
    request: TripEditRequest,
    target_day: DayPlan,
) -> DayEditDraft | None:
    """
    Use LLM structured output to generate a single-day edit draft; return None if it fails.
    """
    llm = _build_chat_llm()
    if llm is None:
        return None

    current_day_payload = {
        "day_index": target_day.day_index,
        "date": target_day.date.isoformat() if target_day.date else None,
        "theme": target_day.theme,
        "spots": [spot.model_dump(mode="json") for spot in target_day.spots],
        "meals": [meal.model_dump(mode="json") for meal in target_day.meals],
        "notes": list(target_day.notes),
    }

    current_itinerary_payload = request.current_itinerary.model_dump(mode="json")

    system_prompt = (
        "You are a travel itinerary editing assistant. "
        "According to the user's editing instructions, rewrite only the core arrangements for the target day. "
        "Keep the edited result aligned with the itinerary's city, budget, and relaxed style."
    )

    human_prompt = f"""
Current completed itinerary:
{json.dumps(current_itinerary_payload, ensure_ascii=False, indent=2)}

Edited target day:
{json.dumps(current_day_payload, ensure_ascii=False, indent=2)}

User instruction: {request.user_instruction}
Edit scope: {request.edit_scope or 'Not specified'}
Constraints to preserve: {', '.join(request.preserve_constraints) if request.preserve_constraints else 'None'}

Requirements:
1. Only output the edited result for the target day.
2. If the user requests a "more relaxed" or "less crowded" experience, reduce fixed attraction pressure and make notes natural.
3. Maintain the original itinerary's city, style, dining tone, and budget structure.
"""

    messages = [
        ("system", system_prompt),
        ("human", human_prompt),
    ]

    print("[trip_planner_agent] Invoking LLM for structured day edit...")
    print(f"[trip_planner_agent] model = {LLM_MODEL}")
    print(f"[trip_planner_agent] base_url = {LLM_BASE_URL or '<DEFAULT>'}")

    try:
        structured_llm = llm.with_structured_output(DayEditDraft)
        raw_result = structured_llm.invoke(messages)
        return (
            raw_result
            if isinstance(raw_result, DayEditDraft)
            else DayEditDraft.model_validate(raw_result)
        )
    except Exception as exc:
        print(
            "[trip_planner_agent] Structured day edit failed, trying raw JSON fallback: "
            f"{type(exc).__name__}: {exc}"
        )
        try:
            response = llm.invoke(messages)
            json_text = _extract_json_object(_extract_raw_text(response))
            if json_text is None:
                return None
            payload = json.loads(json_text)
            if not isinstance(payload, dict):
                raise ValueError("Single day edit result is not a JSON object.")
            return DayEditDraft.model_validate(_normalize_day_edit_payload(payload))
        except Exception as fallback_exc:
            print(
                f"[trip_planner_agent] Single day edit fallback failed: {type(fallback_exc).__name__}: {fallback_exc}"
            )
            return None