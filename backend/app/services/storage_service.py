from contextlib import contextmanager
from datetime import datetime, timezone
import json

from app.core.config import Base, SessionLocal, engine
from app.models.db_models import TripRecord
from app.schemas.trip import Itinerary, TripDetailResponse, TripListResponse, TripSummaryItem


def init_db() -> None:
    """Explicitly initialize database tables (call once at app startup or in test setup)."""
    if engine is None or Base is None or SessionLocal is None:
        raise RuntimeError(
            "Database is not configured because SQLAlchemy is unavailable in the current environment."
        )
    Base.metadata.create_all(bind=engine)


@contextmanager
def _session_scope():
    """Provide a clean SQLAlchemy session with guaranteed cleanup."""
    if SessionLocal is None:
        raise RuntimeError(
            "Database is not configured because SQLAlchemy is unavailable in the current environment."
        )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def save_itinerary(itinerary: Itinerary) -> str:
    """Atomically save or update the complete itinerary and return the trip_id."""
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    now = datetime.now(timezone.utc)
    itinerary_json = json.dumps(
        itinerary.model_dump(mode="json"),
        ensure_ascii=False,
    )

    with _session_scope() as session:
        stmt = sqlite_insert(TripRecord).values(
            trip_id=itinerary.trip_id,
            destination=itinerary.destination,
            summary=itinerary.summary,
            itinerary_json=itinerary_json,
            created_at=now,
            updated_at=now,
        )
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=[TripRecord.trip_id],
            set_={
                "destination": stmt.excluded.destination,
                "summary": stmt.excluded.summary,
                "itinerary_json": stmt.excluded.itinerary_json,
                "updated_at": now,
            },
        )
        session.execute(upsert_stmt)
        session.commit()
        return itinerary.trip_id


def get_itinerary_by_trip_id(trip_id: str) -> TripDetailResponse | None:
    """Read saved itinerary by trip_id, return None if not found."""
    with _session_scope() as session:
        record = session.query(TripRecord).filter(TripRecord.trip_id == trip_id).first()
        if record is None:
            return None

        itinerary_data = json.loads(record.itinerary_json)
        itinerary = Itinerary(**itinerary_data)

        return TripDetailResponse(
            trip_id=record.trip_id,
            itinerary=itinerary,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


def list_saved_itineraries() -> TripListResponse:
    """Return a list of summaries for all saved itineraries."""
    with _session_scope() as session:
        records = (
            session.query(TripRecord)
            .order_by(TripRecord.updated_at.desc(), TripRecord.id.desc())
            .all()
        )

        items = [
            TripSummaryItem(
                trip_id=record.trip_id,
                destination=record.destination,
                summary=record.summary,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for record in records
        ]
        return TripListResponse(total=len(items), items=items)


def delete_itinerary_by_trip_id(trip_id: str) -> bool:
    """Delete a saved itinerary by trip_id, return True if successful."""
    with _session_scope() as session:
        record = session.query(TripRecord).filter(TripRecord.trip_id == trip_id).first()
        if record is None:
            return False

        session.delete(record)
        session.commit()
        return True