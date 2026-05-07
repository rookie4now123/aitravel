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
    """LLM returns draft for a single day from LLM."""

    day_index: int = Field(..., ge=1)
    theme: str = Field(..., description="Short theme for the day, e.g., 'Relaxing Beach Day' or 'Cultural Exploration'.")
    spot_name: str = Field(..., description="Name of the main attraction for the day")
    spot_description: str = Field(..., description="Brief reason for recommending the attraction")
    meal_name: str = Field(..., description="Name of the meal or restaurant for the day")
    meal_notes: str = Field(..., description="Brief notes about the meal")
    daily_note: str = Field(..., description="A brief planning note for the day")


class PlannerDraft(BaseModel):
    """Provide structured trip draft for trip_service.py."""

    summary: str = Field(..., description="Short overview of the entire trip")
    tips: list[str] = Field(default_factory=list, description="Travel tips")
    days: list[PlannerDayDraft] = Field(default_factory=list)


class DayEditDraft(BaseModel):
    """LLM returns draft for editing a single day."""

    theme: str = Field(..., description="Edited theme for the day")
    spot_name: str = Field(..., description="Edited name of the main attraction for the day")
    spot_description: str = Field(..., description="Edited description of the attraction")
    meal_name: str = Field(..., description="Edited name of the meal or restaurant for the day")
    meal_notes: str = Field(..., description="Edited notes about the meal")
    daily_note: str = Field(..., description="Edited planning note for the day")


def _normalize_day_edit_payload(payload: dict) -> dict:
    """Compatible with model returns of two different daily edit formats."""
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
    """Extract JSON object string from raw model text as much as possible."""
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
    """Create instance of ChatOpenAI for general use."""
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
    Generate structured trip draft using LangChain.
    If the current environment is not ready for model invocation, return None,
    allowing the service layer to fall back to the rule-based implementation.
    """
    llm = _build_chat_llm()
    if llm is None:
        return None

    guide_context = "\n\n".join(rag_contexts) if rag_contexts else "No local context"

    system_prompt = (
        "You are a travel planning assistant. "
        "Please generate a concise structured travel draft in europe."
        "You need to follow the user's destination, budget, pace, and local guide context."
        "You must only output one JSON object, do not output Markdown, do not output explanation text, do not output code blocks."
        "The output content must strictly comply with the given structured field requirements."
        "If the user explicitly states specific requests in the additional notes, such as wanting to see the sunset, not wanting to wake up early, preferring less spice, or taking photos, you should prioritize incorporating these requests into the specific attractions or daily plans for a particular day, rather than just writing general tips."
    )

    human_prompt = f"""
Destination: {request.destination}
Start Date: {request.start_date.isoformat()}
End Date: {request.end_date.isoformat()}
Day Count: {day_count}
Travelers: {request.travelers}
Budget: {request.budget}
Preferences: {'、'.join(request.preferences) if request.preferences else 'No special preferences'}
Pace: {request.pace or 'Moderate'}
Dietary Preferences: {'、'.join(request.dietary_preferences) if request.dietary_preferences else 'None'}
Hotel Level: {request.hotel_level or 'Comfortable'}
Additional Notes: {request.special_notes or 'None'}

Local Guide Context:
{guide_context}

Requirements:
1. Output a overall summary.
2. Output the daily draft for {day_count} days.
3. One main attraction, one meal recommendation, and one daily note for each day.
4. tips keep clean。
5. day_index must be from 1 to {day_count}。
6. If there are specific requests in the additional notes, such as wanting to see the sunset or not wanting to wake up early, they must be reflected in the days section, not just placed in the tips.
7. If the plan includes watching the sunset, the spot_name for that day should preferably be a location suitable for watching the sunset, or at least consistent with the sunset arrangement in the daily_note, to avoid a complete disconnect between the "main attraction" and the "sunset location".
8. Everyday's arrangement should follow a "relaxed" pace, avoiding overcrowding and too early departure.
9. Dining recommendations should prioritize that have already appeared in the local guide context.
10. Only return a JSON object, do not return any additional explanations, do not use ```json code blocks.

JSON Sample:
{{
  "summary": "Overall",
  "tips": ["Hint1", "Hint2"],
  "days": [
    {{
      "day_index": 1,
      "theme": "Topic of the day",
      "spot_name": "Main Attraction",
      "spot_description": "Reason for recommendation",
      "meal_name": "Meal Name",
      "meal_notes": "Meal Notes",
      "daily_note": "Daily Note"
    }}
  ]
}}
"""

    print(f"[trip_planner_agent] Ready to invoke LLM...")
    print(f"[trip_planner_agent] model = {LLM_MODEL}")
    print(f"[trip_planner_agent] base_url = {LLM_BASE_URL or '<DEFAULT>'}")
    print(f"[trip_planner_agent] timeout = {LLM_TIMEOUT_SECONDS}s")
    print(f"[trip_planner_agent] max_retries = {LLM_MAX_RETRIES}")

    try:
        response = llm.invoke(
            [
                ("system", system_prompt),
                ("human", human_prompt),
            ]
        )
    except Exception as exc:
        print(f"[trip_planner_agent] Large model invocation failed: {type(exc).__name__}: {exc}")
        return None

    print("[trip_planner_agent] Large model invocation completed.")

    raw_text = getattr(response, "content", "")
    if isinstance(raw_text, list):
        raw_text = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in raw_text
        )

    json_text = _extract_json_object(str(raw_text))
    if json_text is None:
        print("[trip_planner_agent] Failed to extract JSON from model response.")
        print(f"[trip_planner_agent] Primitive return preview {str(raw_text)[:300]}")
        return None

    try:
        result = PlannerDraft.model_validate(json.loads(json_text))
    except Exception as exc:
        print(f"[trip_planner_agent] JSON parsing failed: {type(exc).__name__}: {exc}")
        print(f"[trip_planner_agent] Primitive return preview: {str(raw_text)[:300]}")
        return None

    if len(result.days) != day_count:
        print(
            "[trip_planner_agent] Structured result day count mismatch,"
            f"expected={day_count}, actual={len(result.days)}"
        )
        return None

    return result


def generate_day_edit_draft(
    request: TripEditRequest,
    target_day: DayPlan,
) -> DayEditDraft | None:
    """
    Use LLM to generate a single day edit draft, return None if failed.
    This function is only responsible for producing the edited result for the target day,
    the final merging back to the complete itinerary is handled by the service layer.
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
        "According to the user's editing instructions, only rewrite the core arrangements for the target day. "
        "You must only output a JSON object, do not output Markdown, do not output explanation text, do not output code blocks. "
        "The edited result should keep itinerary style budget and relax "
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
2. If the user requests a "more relaxed" or "less crowded" experience, reduce the pressure of fixed attractions and make notes more natural.
3. Try to maintain the original itinerary's city, style, dining tone, and budget structure.
4. Do not output additional fields.
5. Only return a JSON object.

JSON structure example:
{{
  "theme": "Edited target day theme",
  "spot_name": "Edited main attraction",
  "spot_description": "Edited attraction description",
  "meal_name": "Edited dining name",
  "meal_notes": "Edited dining notes",
  "daily_note": "Edited daily note"
}}
"""

    print("[trip_planner_agent] Invokeing LLM for day edit...")
    print(f"[trip_planner_agent] model = {LLM_MODEL}")
    print(f"[trip_planner_agent] base_url = {LLM_BASE_URL or '<DEFAULT>'}")

    try:
        response = llm.invoke(
            [
                ("system", system_prompt),
                ("human", human_prompt),
            ]
        )
    except Exception as exc:
        print(f"[trip_planner_agent] Failed to invoke day edit: {type(exc).__name__}: {exc}")
        return None

    raw_text = getattr(response, "content", "")
    if isinstance(raw_text, list):
        raw_text = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in raw_text
        )

    json_text = _extract_json_object(str(raw_text))
    if json_text is None:
        print("[trip_planner_agent] Failed to extract JSON from day edit result.")
        print(f"[trip_planner_agent] Raw response preview: {str(raw_text)[:300]}")
        return None

    try:
        payload = json.loads(json_text)
        if not isinstance(payload, dict):
            raise ValueError("Single day edit result is not a JSON object.")
        normalized_payload = _normalize_day_edit_payload(payload)
        return DayEditDraft.model_validate(normalized_payload)
    except Exception as exc:
        print(f"[trip_planner_agent] Single day edit JSON parsing failed: {type(exc).__name__}: {exc}")
        print(f"[trip_planner_agent] Raw response preview: {str(raw_text)[:300]}")
        return None
