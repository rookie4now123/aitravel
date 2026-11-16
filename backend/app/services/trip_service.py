from __future__ import annotations

from datetime import date as DateType, timedelta
import re
import unicodedata
from uuid import uuid4

from app.agents.trip_planner_agent import (
    collect_trip_context,
    generate_day_edit_draft,
    generate_planner_draft,
)
from app.core.config import ENABLE_GOOGLE_MAPS_ENRICHMENT
from app.schemas.trip import (
    BudgetBreakdown,
    DayPlan,
    HotelItem,
    Itinerary,
    MealItem,
    SpotItem,
    TransportItem,
    TripEditRequest,
    TripRequest,
)
from app.services.map_service import enrich_itinerary_with_map_data


TECHNICAL_TIP_PHRASES = (
    "llm",
    "rag",
    "langchain",
    "sqlite",
    "trip_service",
    "source code",
    "rule-based",
    "fallback",
)


def _build_trip_id(destination: str, start_date: DateType) -> str:
    """Create a unique, URL-safe trip_id."""
    ascii_dest = (
        unicodedata.normalize("NFKD", destination)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_dest).strip("-") or "trip"
    return f"trip_{slug}_{start_date.isoformat()}_{uuid4().hex[:8]}"


def _clean_user_tips(tips: list[str], destination: str | None = None) -> list[str]:
    """Filter out internal implementation notes and keep only actionable travel tips."""
    cleaned_tips: list[str] = []
    for tip in tips:
        normalized_tip = tip.strip()
        if not normalized_tip:
            continue
        tip_lower = normalized_tip.lower()
        if any(phrase in tip_lower for phrase in TECHNICAL_TIP_PHRASES):
            continue
        if normalized_tip not in cleaned_tips:
            cleaned_tips.append(normalized_tip)

    if cleaned_tips:
        return cleaned_tips

    place_text = destination or "Destination"
    return [
        f"Prepare rain gear or light jackets based on the real-time weather in {place_text}, as it can feel cooler in the mornings, evenings, and near water.",
        "Older streets, ecological corridors, and stone paths are better explored at a leisurely pace, so it is advisable to choose comfortable and slip-resistant footwear.",
        "Busy attractions are best visited during off-peak hours, allowing for a more relaxed experience with ample time for photos, meals, and transportation.",
    ]


def _build_demo_spot_names(destination: str, rag_contexts: list[str], day_count: int) -> list[str]:
    """Choose plausible fallback spot names from RAG contexts when the LLM draft is unavailable."""
    candidate_names: list[str] = []
    joined_lower = "\n".join(rag_contexts).lower()

    for city in ("Krakow", "Prague", "Madrid", "Paris", "Milan", "Barcelona", "Florence"):
        if city.lower() in joined_lower:
            candidate_names.append(f"{city} old town")

    while len(candidate_names) < day_count:
        candidate_names.append(f"{destination} recommended attractions {len(candidate_names) + 1}")

    return candidate_names[:day_count]


def _stable_bucket(text: str, modulo: int) -> int:
    """Generate a stable bucket value based on the text for deterministic price variation."""
    return sum(ord(char) for char in text) % modulo if modulo > 0 else 0


def _prorate_amounts(total: float, weights: list[float]) -> list[float]:
    """Split the amount according to weights, ensuring the sum equals the original total."""
    if not weights:
        return []

    safe_weights = [max(weight, 0.01) for weight in weights]
    total_cents = max(int(round(total * 100)), 0)
    weight_sum = sum(safe_weights)
    raw_cents = [(total_cents * weight) / weight_sum for weight in safe_weights]
    base_cents = [int(value) for value in raw_cents]
    remainder = total_cents - sum(base_cents)

    ranked_indexes = sorted(
        range(len(raw_cents)),
        key=lambda index: (raw_cents[index] - base_cents[index], -index),
        reverse=True,
    )
    for index in ranked_indexes[:remainder]:
        base_cents[index] += 1

    return [round(value / 100, 2) for value in base_cents]


def _estimate_ticket_cost(spot_name: str, description: str | None = None) -> float:
    """Estimate ticket costs based on spot keywords."""
    text = f"{spot_name} {description or ''}".lower()
    bucket = _stable_bucket(text, 4)

    if any(
        keyword in text
        for keyword in ("old city", "old town", "park", "square", "promenade", "beach", "quarter")
    ):
        return [0.0, 15.0, 25.0, 35.0][bucket]
    if any(
        keyword in text
        for keyword in ("cathedral", "church", "museum", "gallery", "palace", "castle", "ruins")
    ):
        return round(45.0 + (bucket * 15.0), 2)
    if any(
        keyword in text
        for keyword in ("cableway", "cable car", "boat tour", "cruise", "performance", "tower")
    ):
        return round(80.0 + (bucket * 20.0), 2)
    return round(30.0 + (bucket * 10.0), 2)


def _build_hotel_weights(day_count: int, start_date: DateType) -> list[float]:
    """Make hotel costs vary slightly based on weekends and stay pattern."""
    weights: list[float] = []
    for index in range(day_count):
        current_date = start_date + timedelta(days=index)
        weight = 1.0
        if current_date.weekday() in (4, 5):
            weight += 0.18
        if index == day_count - 1:
            weight += 0.08
        if index % 2 == 1:
            weight += 0.05
        weights.append(weight)
    return weights


def _build_meal_weights(day_count: int, preferences: list[str]) -> list[float]:
    """Increase meal budget for users who prefer local cuisine."""
    foodie_bonus = (
        0.12
        if any(p.strip().lower() in ("food", "foodie", "cuisine", "gourmet") for p in preferences)
        else 0.0
    )
    return [
        1.0 + foodie_bonus + (0.08 if index == day_count // 2 else 0.0) + ((index % 3) * 0.04)
        for index in range(day_count)
    ]


def _build_transport_weights(day_count: int, pace: str | None) -> list[float]:
    """Adjust transport budget slightly based on travel pace and first/last days."""
    pace_val = (pace or "").strip().lower()
    if pace_val in ("compact", "tight", "fast"):
        pace_bonus = 0.12
    elif pace_val in ("relax", "relaxed", "leisure", "leisurely"):
        pace_bonus = -0.04
    else:
        pace_bonus = 0.04

    return [
        1.0 + pace_bonus + (0.16 if index in (0, day_count - 1) else 0.0) + (index * 0.03)
        for index in range(day_count)
    ]


def _apply_route_based_transport_costs(itinerary: Itinerary) -> None:
    """If route distances are available, adjust transport costs and durations accordingly."""
    for day in itinerary.days:
        for transport in day.transport:
            if transport.estimated_minutes is not None:
                transport.duration = f"{transport.estimated_minutes} minutes"

            if transport.distance_km is None:
                continue

            mode_l = (transport.mode or "").lower()
            if any(k in mode_l for k in ("bus", "tram", "metro", "subway")):
                cost = max(2.0, 2.0 + (transport.distance_km * 0.25))
            elif "walk" in mode_l:
                cost = 0.0
            elif any(k in mode_l for k in ("charter", "private")):
                cost = 30.0 + (transport.distance_km * 3.8)
            else:
                cost = 10.0 + (transport.distance_km * 2.2)

            transport.estimated_cost = round(cost, 2)


def _refresh_budget_breakdown(itinerary: Itinerary, request_budget: float | None = None) -> Itinerary:
    """Recalculate the total budget from individual line items."""
    _apply_route_based_transport_costs(itinerary)

    transport_total = round(
        sum(item.estimated_cost for day in itinerary.days for item in day.transport),
        2,
    )
    hotel_total = round(
        sum(day.hotel.estimated_cost for day in itinerary.days if day.hotel is not None),
        2,
    )
    meal_total = round(
        sum(item.estimated_cost for day in itinerary.days for item in day.meals),
        2,
    )
    ticket_total = round(
        sum(item.estimated_cost for day in itinerary.days for item in day.spots),
        2,
    )

    subtotal = transport_total + hotel_total + meal_total + ticket_total
    if request_budget is not None:
        other_total = round(max(0.0, min(request_budget * 0.12, request_budget - subtotal)), 2)
    else:
        other_total = round(max(subtotal * 0.06, 0.0), 2)

    total = round(subtotal + other_total, 2)
    itinerary.budget_breakdown = BudgetBreakdown(
        transport=transport_total,
        hotel=hotel_total,
        meals=meal_total,
        tickets=ticket_total,
        other=other_total,
        total=total,
    )
    itinerary.estimated_budget = total
    return itinerary


def _maybe_enrich_itinerary_with_map_data(
    itinerary: Itinerary,
    city: str | None = None,
    request_budget: float | None = None,
) -> Itinerary:
    """Optionally enrich the itinerary with map/route data, then refresh the budget."""
    if ENABLE_GOOGLE_MAPS_ENRICHMENT:
        try:
            itinerary = enrich_itinerary_with_map_data(itinerary, city=city)
        except Exception:
            pass

    return _refresh_budget_breakdown(itinerary, request_budget=request_budget)


def generate_trip_itinerary(request: TripRequest) -> Itinerary:
    """Generate a complete itinerary and produce a realistic budget estimate."""
    day_count = max((request.end_date - request.start_date).days + 1, 1)

    rag_contexts = collect_trip_context(
        destination=request.destination,
        preferences=request.preferences,
        pace=request.pace,
        special_notes=request.special_notes,
    )
    llm_draft = generate_planner_draft(request, rag_contexts, day_count)
    fallback_spot_names = _build_demo_spot_names(request.destination, rag_contexts, day_count)

    raw_days: list[dict[str, object]] = []
    ticket_costs: list[float] = []
    for index in range(day_count):
        day_number = index + 1
        current_date = request.start_date + timedelta(days=index)
        llm_day = None
        if llm_draft is not None:
            llm_day = next((item for item in llm_draft.days if item.day_index == day_number), None)

        spot_name = llm_day.spot_name if llm_day is not None else fallback_spot_names[index]
        theme = (
            llm_day.theme
            if llm_day is not None
            else f"{request.destination} Day {day_number} - relaxed tour"
        )
        spot_description = (
            llm_day.spot_description
            if llm_day is not None
            else "Arranged based on local guides and travel preferences; suitable for a relaxed half-day visit."
        )
        meal_name = llm_day.meal_name if llm_day is not None else f"{request.destination} local cuisine suggestion {day_number}"
        meal_note = (
            llm_day.meal_notes
            if llm_day is not None
            else "A dining suggestion based on user preferences and local guides."
        )
        daily_note = (
            llm_day.daily_note
            if llm_day is not None
            else "Today is planned as a relaxed day; adjust durations based on energy and weather."
        )
        ticket_cost = _estimate_ticket_cost(spot_name, spot_description)

        raw_days.append(
            {
                "day_index": day_number,
                "date": current_date,
                "theme": theme,
                "spot_name": spot_name,
                "spot_description": spot_description,
                "meal_name": meal_name,
                "meal_note": meal_note,
                "daily_note": daily_note,
                "ticket_cost": ticket_cost,
            }
        )
        ticket_costs.append(ticket_cost)

    ticket_total = round(sum(ticket_costs), 2)
    pace_val = (request.pace or "").strip().lower()
    if pace_val in ("relax", "relaxed", "leisure", "leisurely"):
        pace_multiplier = 0.78
    elif pace_val in ("compact", "tight", "fast"):
        pace_multiplier = 0.92
    else:
        pace_multiplier = 0.85

    target_total = request.budget * pace_multiplier
    other_budget = round(request.budget * (0.05 + min(day_count, 4) * 0.01), 2)
    allocatable_budget = max(target_total - ticket_total - other_budget, request.budget * 0.45)

    hotel_level = request.hotel_level or "Comfort"
    hl = hotel_level.strip().lower()
    if any(k in hl for k in ("luxury", "deluxe")):
        hotel_ratio = 0.62
    elif any(k in hl for k in ("premium", "upscale", "high-end")):
        hotel_ratio = 0.56
    elif any(k in hl for k in ("economy", "budget")):
        hotel_ratio = 0.40
    else:
        hotel_ratio = 0.50

    meal_ratio = (
        0.28
        if any(p.strip().lower() in ("food", "foodie", "cuisine", "gourmet") for p in request.preferences)
        else 0.22
    )
    transport_ratio = max(0.12, 1 - hotel_ratio - meal_ratio)
    ratio_sum = hotel_ratio + meal_ratio + transport_ratio

    hotel_total = allocatable_budget * hotel_ratio / ratio_sum
    meal_total = allocatable_budget * meal_ratio / ratio_sum
    transport_total = allocatable_budget * transport_ratio / ratio_sum

    daily_hotel_costs = _prorate_amounts(
        hotel_total,
        _build_hotel_weights(day_count, request.start_date),
    )
    daily_meal_costs = _prorate_amounts(
        meal_total,
        _build_meal_weights(day_count, request.preferences),
    )
    daily_transport_costs = _prorate_amounts(
        transport_total,
        _build_transport_weights(day_count, request.pace),
    )

    days: list[DayPlan] = []
    for index, raw_day in enumerate(raw_days):
        spot_name = str(raw_day["spot_name"])
        day_plan = DayPlan(
            day_index=int(raw_day["day_index"]),
            date=raw_day["date"],
            theme=str(raw_day["theme"]),
            spots=[
                SpotItem(
                    name=spot_name,
                    start_time="10:00",
                    end_time="12:00",
                    description=str(raw_day["spot_description"]),
                    estimated_cost=float(raw_day["ticket_cost"]),
                    location=request.destination,
                )
            ],
            meals=[
                MealItem(
                    name=str(raw_day["meal_name"]),
                    meal_type="lunch",
                    estimated_cost=daily_meal_costs[index],
                    notes=str(raw_day["meal_note"]),
                )
            ],
            hotel=HotelItem(
                name=f"{request.destination} {hotel_level} accommodation {index + 1}",
                level=hotel_level,
                estimated_cost=daily_hotel_costs[index],
                location=f"{request.destination} downtown",
            ),
            transport=[
                TransportItem(
                    mode="taxi",
                    from_place=f"Starting point in {request.destination}",
                    to_place=spot_name,
                    estimated_cost=daily_transport_costs[index],
                    duration="30 minutes",
                )
            ],
            notes=[
                f"Current travel pace: {request.pace or 'moderate'}",
                str(raw_day["daily_note"]),
            ],
        )
        days.append(day_plan)

    preference_text = ", ".join(request.preferences) if request.preferences else "standard travel experience"
    source_notes = [
        "Itinerary is assembled by trip_service.py.",
    ]
    source_notes.extend(rag_contexts[:2])

    tips = (
        llm_draft.tips
        if llm_draft is not None and llm_draft.tips
        else [
            f"Prepare rain gear or a light jacket based on real-time weather in {request.destination}.",
            "Older streets, ecological corridors, and stone paths are best explored at a leisurely pace—choose comfortable, non-slip footwear.",
        ]
    )
    if any(("riding" in (context or "").lower()) or any(k in (context or "").lower() for k in ("cycle", "cycling", "bike")) for context in rag_contexts):
        tips.append("Local guides mention nearby cycling routes suitable for riding; consider as a backup for day 2 or 3.")
    tips = _clean_user_tips(tips, request.destination)

    summary = (
        llm_draft.summary
        if llm_draft is not None
        else f"This is a {day_count}-day itinerary for {request.destination} with preference focus: {preference_text}."
    )

    itinerary = Itinerary(
        trip_id=_build_trip_id(request.destination, request.start_date),
        destination=request.destination,
        summary=summary,
        days=days,
        estimated_budget=0.0,
        budget_breakdown=BudgetBreakdown(),
        tips=tips,
        source_notes=source_notes,
    )
    return _maybe_enrich_itinerary_with_map_data(
        itinerary,
        city=request.destination,
        request_budget=request.budget,
    )


def _clear_spot_geo_fields(spot: SpotItem) -> None:
    """Clear stale location/image metadata when a spot is replaced."""
    spot.image_url = None
    spot.address = None
    spot.latitude = None
    spot.longitude = None
    spot.poi_id = None


def edit_trip_itinerary(request: TripEditRequest) -> Itinerary:
    """Prefer using an LLM to edit a single day's plan; fall back to rule-based edits if unsuccessful."""
    updated_itinerary = request.current_itinerary.model_copy(deep=True)
    if request.trip_id:
        updated_itinerary.trip_id = request.trip_id

    target_day = updated_itinerary.days[0] if updated_itinerary.days else None
    if request.edit_scope and request.edit_scope.startswith("day_"):
        try:
            target_day_index = int(request.edit_scope.split("_")[1])
            matched_day = next(
                (day for day in updated_itinerary.days if day.day_index == target_day_index),
                None,
            )
            if matched_day is not None:
                target_day = matched_day
        except (IndexError, ValueError):
            pass

    if target_day is not None:
        day_edit_draft = generate_day_edit_draft(request, target_day)
        if day_edit_draft is not None:
            target_day.theme = day_edit_draft.theme
            if target_day.spots:
                target_day.spots[0].name = day_edit_draft.spot_name
                target_day.spots[0].description = day_edit_draft.spot_description
                target_day.spots[0].estimated_cost = _estimate_ticket_cost(
                    day_edit_draft.spot_name,
                    day_edit_draft.spot_description,
                )
                _clear_spot_geo_fields(target_day.spots[0])
            if target_day.meals:
                target_day.meals[0].name = day_edit_draft.meal_name
                target_day.meals[0].notes = day_edit_draft.meal_notes

            if target_day.notes:
                target_day.notes[-1] = day_edit_draft.daily_note
            else:
                target_day.notes.append(day_edit_draft.daily_note)
        else:
            inst_l = (request.user_instruction or "").lower()
            if any(k in inst_l for k in ("relax", "relaxed", "leisure")):
                target_day.theme = f"{target_day.theme} (adjusted to be more relaxed)"
                target_day.notes.append("Pace adjusted to be more relaxed per user request.")

            if any(
                k in inst_l
                for k in ("no arrangement", "no arrangements", "no plan", "free activity", "free time")
            ) and target_day.spots:
                target_day.spots[0].name = "Free activity / Flexible schedule"
                target_day.spots[0].description = "Per user request, reduced fixed attractions and preserved more free time."
                target_day.spots[0].estimated_cost = 0.0
                _clear_spot_geo_fields(target_day.spots[0])

    updated_itinerary.source_notes.append(
        f"Itinerary updated per user edit instruction: {request.user_instruction}"
    )
    updated_itinerary.tips = _clean_user_tips(
        updated_itinerary.tips,
        updated_itinerary.destination,
    )
    updated_itinerary.tips.append(
        "Updated target dates per your edits; please reconfirm transportation, weather, and attraction opening times before departure."
    )

    reference_budget = (
        updated_itinerary.estimated_budget
        or updated_itinerary.budget_breakdown.total
        or None
    )
    return _maybe_enrich_itinerary_with_map_data(
        updated_itinerary,
        city=updated_itinerary.destination,
        request_budget=reference_budget,
    )