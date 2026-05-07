from fastapi import APIRouter

from app.api.routes.export import router as export_router
from app.api.routes.trip import router as trip_router
from app.api.routes.weather import router as weather_router


api_router = APIRouter()
api_router.include_router(trip_router)
api_router.include_router(export_router)
api_router.include_router(weather_router)
