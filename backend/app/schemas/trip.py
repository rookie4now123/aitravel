from __future__ import annotations

from datetime import date as DateType, datetime

from pydantic import BaseModel, Field


class TripRequest(BaseModel):
    """Generate a new trip based on the user's input. The request should include all necessary information for trip generation, such as destination, dates, preferences, etc. The response will be a complete itinerary that can be directly used or further edited."""

    destination: str = Field(..., description="Destination, e.g., Krakow")
    start_date: DateType = Field(..., description="Start date of the trip")
    end_date: DateType = Field(..., description="End date of the trip")
    travelers: int = Field(..., ge=1, description="Number of travelers")
    budget: float = Field(..., ge=0, description="Total budget")
    preferences: list[str] = Field(default_factory=list, description="Travel preference tags")
    pace: str | None = Field(default=None, description="Pace of the trip, e.g., relaxed, moderate, fast")
    dietary_preferences: list[str] = Field(
        default_factory=list,
        description="Dietary preferences or restrictions",
    )
    hotel_level: str | None = Field(default=None, description="Hotel level preference")
    special_notes: str | None = Field(default=None, description="Special notes or requirements")


class TripEditRequest(BaseModel):
    """Modify the itinerary request"""

    trip_id: str = Field(..., description="Trip ID to be edited")
    current_itinerary: "Itinerary" = Field(..., description="Current complete itinerary")
    user_instruction: str = Field(..., description="User's new modification request")
    edit_scope: str | None = Field(default=None, description="Scope of the edit")
    preserve_constraints: list[str] = Field(
        default_factory=list,
        description="Conditions to be preserved as much as possible",
    )


class TripSaveRequest(BaseModel):
    """Save request for the current itinerary."""

    trip_id: str = Field(..., description="ID of the itinerary to be saved")
    itinerary: "Itinerary" = Field(..., description="Complete itinerary data")
    user_id: str | None = Field(default=None, description="User ID, optional for the current version")


class SpotItem(BaseModel):
    """Single spot"""

    name: str = Field(..., description="Spot name")
    start_time: str | None = Field(default=None, description="Start time")
    end_time: str | None = Field(default=None, description="End time")
    description: str | None = Field(default=None, description="Spot arrangement description")
    estimated_cost: float = Field(default=0.0, ge=0, description="Estimated cost")
    location: str | None = Field(default=None, description="Spot location description")
    image_url: str | None = Field(default=None, description="Spot image URL")
    address: str | None = Field(default=None, description="Spot detailed address")
    latitude: float | None = Field(default=None, description="Spot latitude")
    longitude: float | None = Field(default=None, description="Spot longitude")
    poi_id: str | None = Field(default=None, description="POI ID returned by the map service")


class MealItem(BaseModel):
    """Single meal arrangement."""

    name: str = Field(..., description="Restaurant or meal suggestion name")
    meal_type: str = Field(..., description="Breakfast, lunch, dinner, etc.")
    estimated_cost: float = Field(default=0.0, ge=0, description="Estimated cost")
    notes: str | None = Field(default=None, description="Additional notes")

class HotelItem(BaseModel):
    """Single hotel arrangement."""

    name: str = Field(..., description="Hotel name")
    level: str | None = Field(default=None, description="Hotel level")
    estimated_cost: float = Field(default=0.0, ge=0, description="Estimated cost")
    location: str | None = Field(default=None, description="Hotel location")
    address: str | None = Field(default=None, description="Hotel detailed address")
    latitude: float | None = Field(default=None, description="Hotel latitude")
    longitude: float | None = Field(default=None, description="Hotel longitude")


class TransportItem(BaseModel):
    """Single transport arrangement."""

    mode: str = Field(..., description="Transport mode, e.g., walking, taxi, bus")
    from_place: str | None = Field(default=None, description="Departure place")
    to_place: str | None = Field(default=None, description="Destination")
    estimated_cost: float = Field(default=0.0, ge=0, description="Estimated cost")
    duration: str | None = Field(default=None, description="Expected duration")
    distance_km: float | None = Field(default=None, ge=0, description="Expected distance, in kilometers")
    estimated_minutes: int | None = Field(default=None, ge=0, description="Expected duration, in minutes")


class BudgetBreakdown(BaseModel):
    """Budget breakdown."""

    transport: float = Field(default=0.0, ge=0, description="Transport budget")
    hotel: float = Field(default=0.0, ge=0, description="Accommodation budget")
    meals: float = Field(default=0.0, ge=0, description="Meals budget")
    tickets: float = Field(default=0.0, ge=0, description="Tickets budget")
    other: float = Field(default=0.0, ge=0, description="Other budget")
    total: float = Field(default=0.0, ge=0, description="Total budget")


class DayPlan(BaseModel):
    """Single day itinerary."""

    day_index: int = Field(..., ge=1, description="Day index")
    date: DateType | None = Field(default=None, description="Current Date")
    theme: str | None = Field(default=None, description="Current Topic")
    spots: list[SpotItem] = Field(default_factory=list, description="Spots")
    meals: list[MealItem] = Field(default_factory=list, description="Meals")
    hotel: HotelItem | None = Field(default=None, description="Hotel")
    transport: list[TransportItem] = Field(default_factory=list, description="Transport")
    notes: list[str] = Field(default_factory=list, description="Notes")


class Itinerary(BaseModel):
    """Completed Itinerary"""

    trip_id: str = Field(..., description="Unique tag")
    destination: str = Field(..., description="Destination")
    summary: str = Field(..., description="Trip overview")
    days: list[DayPlan] = Field(default_factory=list, description="Daily itineraries")
    estimated_budget: float = Field(default=0.0, ge=0, description="Total budget")
    budget_breakdown: BudgetBreakdown = Field(..., description="Budget breakdown")
    tips: list[str] = Field(default_factory=list, description="Travel tips")
    source_notes: list[str] = Field(
        default_factory=list,
        description="RAG or explainations",
    )


class TripDetailResponse(BaseModel):
    """Search returned response when querying saved itinerary by trip_id."""

    trip_id: str = Field(..., description="Itinerary ID")
    itinerary: Itinerary = Field(..., description="Completed Itinerary")
    created_at: datetime | None = Field(default=None, description="Creation Time")
    updated_at: datetime | None = Field(default=None, description="Update Time")


class TripSummaryItem(BaseModel):
    """Summary information of the saved itinerary."""

    trip_id: str = Field(..., description="Itinerary ID")
    destination: str = Field(..., description="Destination")
    summary: str = Field(..., description="Trip overview")
    created_at: datetime | None = Field(default=None, description="Creation Time")
    updated_at: datetime | None = Field(default=None, description="Update Time")


class TripListResponse(BaseModel):
    """Search response structure for itinerary list."""

    total: int = Field(..., ge=0, description="List Sum")
    items: list[TripSummaryItem] = Field(default_factory=list, description="Itinerary Summary List")
