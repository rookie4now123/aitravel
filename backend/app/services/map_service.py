from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import (
    GOOGLE_MAPS_API_KEY,
    GOOGLE_MAPS_BASE_URL,
    GOOGLE_MAPS_DEFAULT_CITY,
    GOOGLE_MAPS_TIMEOUT_SECONDS,
    REDIS_MAP_TTL_SECONDS,
)
from app.schemas.trip import HotelItem, Itinerary, SpotItem, TransportItem
from app.services.cache_service import get_cached_json, set_cached_json


logger = logging.getLogger(__name__)


def _ensure_google_maps_api_key() -> None:
    """Make sure Google Maps API Key is configured."""
    if not GOOGLE_MAPS_API_KEY:
        raise RuntimeError(
            "Current environment is not configured with GOOGLE_MAPS_API_KEY, cannot call Google Maps service."
        )


def _build_client() -> httpx.Client:
    """Create Google Maps HTTP API Client."""
    return httpx.Client(timeout=GOOGLE_MAPS_TIMEOUT_SECONDS)


def _request_google_maps(
    path: str,
    params: dict[str, Any],
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Call Google Maps Web Service API and return JSON, optionally reusing an httpx.Client."""
    _ensure_google_maps_api_key()

    base_url = GOOGLE_MAPS_BASE_URL.rstrip("/")
    request_params = {
        **params,
        "key": GOOGLE_MAPS_API_KEY,
    }

    if client is not None:
        response = client.get(f"{base_url}{path}", params=request_params)
        response.raise_for_status()
        payload = response.json()
    else:
        with _build_client() as local_client:
            response = local_client.get(f"{base_url}{path}", params=request_params)
            response.raise_for_status()
            payload = response.json()

    status = payload.get("status")
    if status not in ("OK", "ZERO_RESULTS"):
        error_msg = payload.get("error_message") or status or "Unknown error"
        raise RuntimeError(f"Google Maps API failed ({status}): {error_msg}")

    return payload


def _parse_float(value: Any) -> float | None:
    """Convert value to float safely."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_cache_text(value: str | None) -> str:
    """Normalize the text used in cache keys."""
    if value is None:
        return ""
    return value.strip().lower()


def _extract_address_component(components: list[dict[str, Any]], *target_types: str) -> str | None:
    """Extract the first matching address component long_name from Google Geocoding results."""
    for component in components:
        types = component.get("types", [])
        if any(target in types for target in target_types):
            return component.get("long_name")
    return None


def _build_photo_url(photos: Any) -> str | None:
    """Build a Google Places Photo URL if a photo_reference is present."""
    if not isinstance(photos, list) or not photos:
        return None
    first_photo = photos[0]
    if not isinstance(first_photo, dict):
        return None
    photo_ref = first_photo.get("photo_reference")
    if not photo_ref or not GOOGLE_MAPS_API_KEY:
        return None
    base_url = GOOGLE_MAPS_BASE_URL.rstrip("/")
    return f"{base_url}/place/photo?maxwidth=800&photo_reference={photo_ref}&key={GOOGLE_MAPS_API_KEY}"


def geocode_address(
    address: str,
    city: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any] | None:
    """Get latitude and longitude information based on the address."""
    target_city = city or GOOGLE_MAPS_DEFAULT_CITY
    cache_key = f"map:geocode:{_normalize_cache_text(address)}:{_normalize_cache_text(target_city)}"
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("map geocode cache hit: address=%s city=%s", address, target_city)
        return cached_value
    logger.info("map geocode cache miss: address=%s city=%s", address, target_city)

    query_address = (
        f"{address}, {target_city}"
        if target_city and target_city.lower() not in address.lower()
        else address
    )
    payload = _request_google_maps(
        "/geocode/json",
        {
            "address": query_address,
            "language": "en",
        },
        client=client,
    )

    results = payload.get("results", [])
    if not results:
        return None

    first = results[0]
    location = first.get("geometry", {}).get("location", {})
    components = first.get("address_components", [])

    result = {
        "formatted_address": first.get("formatted_address", address),
        "province": _extract_address_component(components, "administrative_area_level_1"),
        "city": _extract_address_component(components, "locality", "postal_town", "administrative_area_level_2"),
        "district": _extract_address_component(components, "sublocality", "neighborhood"),
        "country": _extract_address_component(components, "country"),
        "adcode": None,
        "place_id": first.get("place_id"),
        "latitude": _parse_float(location.get("lat")),
        "longitude": _parse_float(location.get("lng")),
    }
    set_cached_json(cache_key, result, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return result


def search_places(
    keyword: str,
    city: str | None = None,
    page_size: int = 5,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Search for POIs based on a keyword using Google Places Text Search."""
    target_city = city or GOOGLE_MAPS_DEFAULT_CITY
    cache_key = (
        f"map:place:{_normalize_cache_text(keyword)}:{_normalize_cache_text(target_city)}:{page_size}"
    )
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("map place cache hit: keyword=%s city=%s", keyword, target_city)
        return cached_value
    logger.info("map place cache miss: keyword=%s city=%s", keyword, target_city)

    query = (
        f"{keyword} in {target_city}"
        if target_city and target_city.lower() not in keyword.lower()
        else keyword
    )
    payload = _request_google_maps(
        "/place/textsearch/json",
        {
            "query": query,
            "language": "en",
        },
        client=client,
    )

    pois = payload.get("results", [])[:page_size]
    results: list[dict[str, Any]] = []
    for poi in pois:
        location = poi.get("geometry", {}).get("location", {})
        types = poi.get("types", [])
        results.append(
            {
                "name": poi.get("name"),
                "address": poi.get("formatted_address"),
                "cityname": target_city,
                "adname": None,
                "type": ", ".join(types) if isinstance(types, list) else None,
                "poi_id": poi.get("place_id"),
                "image_url": _build_photo_url(poi.get("photos")),
                "latitude": _parse_float(location.get("lat")),
                "longitude": _parse_float(location.get("lng")),
                "rating": _parse_float(poi.get("rating")),
            }
        )

    set_cached_json(cache_key, results, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return results


def estimate_route(
    origin_longitude: float,
    origin_latitude: float,
    destination_longitude: float,
    destination_latitude: float,
    client: httpx.Client | None = None,
) -> dict[str, Any] | None:
    """Estimate the driving distance and duration between two points via Google Directions API."""
    cache_key = (
        "map:route:"
        f"{origin_longitude:.6f},{origin_latitude:.6f}:"
        f"{destination_longitude:.6f},{destination_latitude:.6f}"
    )
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info(
            "map route cache hit: origin=%s,%s destination=%s,%s",
            origin_latitude,
            origin_longitude,
            destination_latitude,
            destination_longitude,
        )
        return cached_value
    logger.info(
        "map route cache miss: origin=%s,%s destination=%s,%s",
        origin_latitude,
        origin_longitude,
        destination_latitude,
        destination_longitude,
    )

    payload = _request_google_maps(
        "/directions/json",
        {
            "origin": f"{origin_latitude},{origin_longitude}",
            "destination": f"{destination_latitude},{destination_longitude}",
            "mode": "driving",
            "units": "metric",
        },
        client=client,
    )

    routes = payload.get("routes", [])
    if not routes:
        return None

    legs = routes[0].get("legs", [])
    if not legs:
        return None

    first_leg = legs[0]
    distance_meters = _parse_float(first_leg.get("distance", {}).get("value"))
    duration_seconds = _parse_float(first_leg.get("duration", {}).get("value"))

    result = {
        "distance_meters": distance_meters,
        "distance_km": round(distance_meters / 1000, 2) if distance_meters is not None else None,
        "duration_seconds": duration_seconds,
        "estimated_minutes": round(duration_seconds / 60) if duration_seconds is not None else None,
        "taxi_cost": None,
    }
    set_cached_json(cache_key, result, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return result


def _pick_best_place(
    keyword: str,
    city: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any] | None:
    """Select the best place from POI search results, prefer the first one."""
    results = search_places(keyword=keyword, city=city, page_size=1, client=client)
    if not results:
        return None
    return results[0]


def _enrich_spot(
    spot: SpotItem,
    city: str | None = None,
    client: httpx.Client | None = None,
) -> bool:
    """Complete the address, latitude, longitude, and POI information of a single spot."""
    place = _pick_best_place(spot.name, city=city, client=client)
    if place is None and spot.location:
        place = _pick_best_place(spot.location, city=city, client=client)

    if place is None:
        query_address = spot.address or spot.location or spot.name
        geocode = geocode_address(query_address, city=city, client=client)
        if geocode is None:
            return False
        spot.address = geocode.get("formatted_address") or spot.address
        spot.latitude = geocode.get("latitude")
        spot.longitude = geocode.get("longitude")
        spot.poi_id = geocode.get("place_id") or spot.poi_id
        return True

    spot.address = place.get("address") or spot.address
    spot.image_url = place.get("image_url") or spot.image_url
    spot.latitude = place.get("latitude")
    spot.longitude = place.get("longitude")
    spot.poi_id = place.get("poi_id") or spot.poi_id
    return True


def _enrich_hotel(
    hotel: HotelItem,
    city: str | None = None,
    client: httpx.Client | None = None,
) -> bool:
    """Complete the address and coordinates of a single hotel."""
    place = _pick_best_place(hotel.name, city=city, client=client)
    if place is None and hotel.location:
        place = _pick_best_place(hotel.location, city=city, client=client)

    if place is None:
        query_address = hotel.address or hotel.location or hotel.name
        geocode = geocode_address(query_address, city=city, client=client)
        if geocode is None:
            return False
        hotel.address = geocode.get("formatted_address") or hotel.address
        hotel.latitude = geocode.get("latitude")
        hotel.longitude = geocode.get("longitude")
        return True

    hotel.address = place.get("address") or hotel.address
    hotel.latitude = place.get("latitude")
    hotel.longitude = place.get("longitude")
    return True


def _geocode_place_text(
    place_text: str | None,
    city: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any] | None:
    """Attempt to parse a text-based place into a result with coordinates."""
    if not place_text:
        return None

    place = _pick_best_place(place_text, city=city, client=client)
    if place is not None:
        return {
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
            "address": place.get("address"),
        }

    geocode = geocode_address(place_text, city=city, client=client)
    if geocode is not None:
        return {
            "latitude": geocode.get("latitude"),
            "longitude": geocode.get("longitude"),
            "address": geocode.get("formatted_address"),
        }
    return None


def _enrich_transport(
    transport: TransportItem,
    city: str | None = None,
    client: httpx.Client | None = None,
) -> bool:
    """Complete the distance and duration information of a single transport segment."""
    origin = _geocode_place_text(transport.from_place, city=city, client=client)
    destination = _geocode_place_text(transport.to_place, city=city, client=client)
    if not origin or not destination:
        return False

    if origin.get("latitude") is None or origin.get("longitude") is None:
        return False
    if destination.get("latitude") is None or destination.get("longitude") is None:
        return False

    route = estimate_route(
        origin_longitude=origin["longitude"],
        origin_latitude=origin["latitude"],
        destination_longitude=destination["longitude"],
        destination_latitude=destination["latitude"],
        client=client,
    )
    if route is None:
        return False

    transport.distance_km = route.get("distance_km")
    transport.estimated_minutes = route.get("estimated_minutes")
    if route.get("estimated_minutes") is not None and not transport.duration:
        transport.duration = f"{route['estimated_minutes']} minutes"
    return True


def enrich_itinerary_with_map_data(itinerary: Itinerary, city: str | None = None) -> Itinerary:
    """Use Google Maps to complete the map fields in the itinerary, reusing one HTTP client."""
    enriched_count = 0

    with _build_client() as client:
        for day in itinerary.days:
            for spot in day.spots:
                try:
                    if _enrich_spot(spot, city=city or itinerary.destination, client=client):
                        enriched_count += 1
                except Exception:
                    continue

            if day.hotel is not None:
                try:
                    if _enrich_hotel(day.hotel, city=city or itinerary.destination, client=client):
                        enriched_count += 1
                except Exception:
                    pass

            for transport in day.transport:
                try:
                    if _enrich_transport(transport, city=city or itinerary.destination, client=client):
                        enriched_count += 1
                except Exception:
                    continue

    if enriched_count > 0:
        note = "Google Maps address, coordinates, or route estimation information completed."
        if note not in itinerary.source_notes:
            itinerary.source_notes.append(note)

    return itinerary