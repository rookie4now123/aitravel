from fastapi import APIRouter, HTTPException

from app.schemas.trip import (
    Itinerary,
    TripDetailResponse,
    TripEditRequest,
    TripListResponse,
    TripRequest,
    TripSaveRequest,
)
from app.services.storage_service import (
    delete_itinerary_by_trip_id,
    get_itinerary_by_trip_id,
    list_saved_itineraries,
    save_itinerary,
)
from app.services.trip_service import edit_trip_itinerary, generate_trip_itinerary


router = APIRouter(prefix="/trip", tags=["trip"])


@router.get("", response_model=TripListResponse)
def list_trips() -> TripListResponse:
    """Return to the saved itinerary summary list."""
    return list_saved_itineraries()


@router.post("/generate", response_model=Itinerary)
def generate_trip(request: TripRequest) -> Itinerary:
    """Generate structured itinerary."""
    return generate_trip_itinerary(request)


@router.post("/edit", response_model=Itinerary)
def edit_trip(request: TripEditRequest) -> Itinerary:
    """Export updated itinerary based on user edit instructions."""
    return edit_trip_itinerary(request)


@router.post("/save")
def save_trip(request: TripSaveRequest) -> dict[str, str]:
    """Save itinerary and return trip_id."""
    saved_trip_id = save_itinerary(request.itinerary)
    return {
        "message": "Trip itinerary saved successfully.",
        "trip_id": saved_trip_id,
    }


@router.get("/{trip_id}", response_model=TripDetailResponse)
def get_trip_detail(trip_id: str) -> TripDetailResponse:
    """Query saved itinerary by trip_id."""
    trip_detail = get_itinerary_by_trip_id(trip_id)
    if trip_detail is None:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return trip_detail


@router.delete("/{trip_id}")
def delete_trip(trip_id: str) -> dict[str, str]:
    """Delete saved itinerary by trip_id."""
    deleted = delete_itinerary_by_trip_id(trip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return {
        "message": "Trip itinerary deleted successfully.",
        "trip_id": trip_id,
    }
