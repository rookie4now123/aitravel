import os
from pathlib import Path

from dotenv import load_dotenv

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import declarative_base, sessionmaker
except ImportError:
    create_engine = None
    declarative_base = None
    sessionmaker = None


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")


# Database configuration
DB_DIR = BACKEND_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)

SQLITE_DB_PATH = DB_DIR / "app.db"
DATABASE_URL = f"sqlite:///{SQLITE_DB_PATH.as_posix()}"

if create_engine is not None and sessionmaker is not None and declarative_base is not None:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
else:
    engine = None
    SessionLocal = None
    Base = None


# LLM configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini compatible")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))


# RAG / local guide search configuration
_rag_sqlite_db_path_raw = Path(os.getenv("RAG_SQLITE_DB_PATH", "db/rag.sqlite3"))
RAG_SQLITE_DB_PATH = (
    _rag_sqlite_db_path_raw
    if _rag_sqlite_db_path_raw.is_absolute()
    else BACKEND_DIR / _rag_sqlite_db_path_raw
)


# Redis / cache configuration
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "trip_planner")
REDIS_DEFAULT_TTL_SECONDS = int(os.getenv("REDIS_DEFAULT_TTL_SECONDS", "1800"))
REDIS_WEATHER_TTL_SECONDS = int(os.getenv("REDIS_WEATHER_TTL_SECONDS", "1800"))
REDIS_MAP_TTL_SECONDS = int(os.getenv("REDIS_MAP_TTL_SECONDS", "86400"))
REDIS_RAG_TTL_SECONDS = int(os.getenv("REDIS_RAG_TTL_SECONDS", "21600"))


# Google Maps configuration
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
GOOGLE_MAPS_BASE_URL = os.getenv("GOOGLE_MAPS_BASE_URL", "https://www.google.com/maps")
GOOGLE_MAPS_DEFAULT_CITY = os.getenv("GOOGLE_MAPS_DEFAULT_CITY", "Krakow")
GOOGLE_MAPS_TIMEOUT_SECONDS = int(os.getenv("GOOGLE_MAPS_TIMEOUT_SECONDS", "20"))
ENABLE_GOOGLE_MAPS_ENRICHMENT = os.getenv("ENABLE_GOOGLE_MAPS_ENRICHMENT", "false").lower() == "true"
