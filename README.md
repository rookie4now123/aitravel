# 🗺️ AI Travel Planner

> An intelligent travel planning system integrating LLMs, RAG, local travel guides, and map services.

**AI Travel Planner** is a sophisticated AI-driven application designed to streamline travel planning. By taking user inputs—destination, dates, budget, group size, and personal preferences—the system generates a structured, multi-day itinerary. It goes beyond simple text generation by enriching plans with real-world map data, weather forecasts, budget breakdowns, and exportable documents.

Unlike standard LLM demos, this project focuses on a complete end-to-end product experience: from **itinerary generation and RAG-enhanced local recommendations to map visualization, weather integration, and document management**.

---

## ✨ Key Features

- 🧠 **AI-Powered Planning**: Leverages Large Language Models (LLM) via LangChain to create structured, coherent travel plans. Supports multiple providers like DashScope (Qwen), Gemini, and OpenAI-compatible APIs.
- 📚 **RAG-Enhanced Local Guides**: Uses a Retrieval-Augmented Generation (RAG) system powered by **SQLite FTS** to inject local travel expertise (from Markdown guides) into the AI's planning process, ensuring accurate and localized suggestions.
- 🗺️ **Intelligent Map Enrichment**: Automatically complements attractions with addresses, coordinates, POI IDs, and images. Supports route visualization with dashed arrows and打卡 (check-in) markers on the map.
- 🌦️ **Weather-Aware Planning**: Integrates real-time weather forecasts to provide context-aware travel tips (e.g., suggesting indoor activities on rainy days).
- 💰 **Detailed Budgeting**: Provides a granular breakdown of costs across transportation, accommodation, meals, tickets, and miscellaneous expenses, both daily and for the entire trip.
- 🪄 **Natural Language Editing**: Allows users to refine their itinerary using natural language (e.g., "Make Day 2 more relaxed" or "Swap lunch with a seafood place").
- 🗂️ **History Management**: Comprehensive system for saving, viewing, and managing past itineraries.
- 📄 **Multi-Format Export**: Supports exporting itineraries to **Markdown** and **PDF** (rendered with ReportLab) for offline use.
- ⚡ **Redis Caching Layer**: High-performance caching for weather data, map queries, and RAG retrieval results to minimize external API latency and costs.

---

## 🏗️ Technical Architecture

### Tech Stack

- **Backend**: FastAPI (Python), SQLAlchemy, Pydantic, HTTPX.
- **Frontend**: React 19, Vite, TanStack Router, Tailwind CSS 4, Radix UI.
- **LLM/AI**: LangChain, DashScope (Qwen) / Gemini / OpenAI.
- **Vector/Search**: SQLite FTS (Full-Text Search) for local RAG.
- **Persistence**: SQLite (Application DB).
- **Cache**: Redis.
- **Maps**: Map Service Integration (supporting Geocoding, POI, Routing, and Images).

### System Data Flow

1.  **Input**: The user provides trip details through the React-based planning interface.
2.  **Generation**: The backend invokes a LangChain Agent, which performs:
    *   **Query Rewrite**: Refines user input into search-friendly queries.
    *   **RAG Retrieval**: Searches local Markdown guides via SQLite FTS for relevant context.
    *   **LLM Synthesis**: Generates a structured JSON draft of the itinerary.
3.  **Enrichment**:
    *   **Map Service**: Fetches coordinates, addresses, and images for all suggested locations.
    *   **Weather Service**: Retrieves forecast data for the destination.
4.  **Presentation**: The final enriched itinerary is displayed on an interactive result page with a map and budget dashboard.
5.  **Persistence/Export**: Users can save the trip to the history or export it as a PDF/Markdown file.

---

## 📁 Project Structure

```text
aitravel/
├── backend/
│   ├── app/
│   │   ├── agents/            # LLM generation and RAG tools
│   │   ├── api/               # FastAPI routes and endpoints
│   │   ├── core/              # Global configuration and environment handling
│   │   ├── models/            # SQLAlchemy database models
│   │   ├── rag/               # SQLite FTS search and ingestion logic
│   │   ├── schemas/           # Pydantic data models (Request/Response)
│   │   └── services/          # Core business logic (Maps, Weather, Export, Storage)
│   ├── data/                  # Local travel guides (Markdown)
│   ├── db/                    # SQLite database files
│   ├── scripts/               # Ingestion, evaluation, and debug scripts
│   └── .env.example           # Backend environment template
├── frontend/
│   ├── src/
│   │   ├── components/        # React components (including Map visualization)
│   │   ├── services/          # API client (Axios)
│   │   ├── views/             # Main pages (Home, Result, History)
│   │   └── App.tsx            # Main entry and routing
│   ├── .env.example           # Frontend environment template
│   └── package.json           # Frontend dependencies and scripts
└── CHANGELOG.md               # Project update history
```

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.9+
- Node.js 18+
- Redis (Optional, but recommended for caching)

### 2. Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and fill in your API keys (LLM, Maps, etc.)

# Ingest travel guide data for RAG
python scripts/ingest_data.py

# Start the server
uvicorn app.api.main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend
npm install

# Configure environment variables
cp .env.example .env
# Edit .env: VITE_API_BASE_URL=http://localhost:8000

# Start the development server
npm run dev
```
Open `http://localhost:3000` (or the port shown in your terminal) to start planning!

---

## 🔐 Environment Highlights

### Backend (`backend/.env`)
- `LLM_PROVIDER`: Choose your provider (e.g., `gemini`, `dashscope`).
- `LLM_API_KEY`: Your model API key.
- `RAG_SQLITE_DB_PATH`: Path to the SQLite FTS database.
- `GOOGLE_MAPS_API_KEY`: Map service API key (Note: Code uses Amap-compatible logic).
- `REDIS_ENABLED`: Set to `true` to enable caching.

### Frontend (`frontend/.env`)
- `VITE_API_BASE_URL`: URL of your backend API.
- `VITE_AMAP_JS_KEY`: JavaScript API key for the map component.

---

---

## 🛣️ Roadmap

- [x] **Phase 1**: Core generation engine, RAG integration, and React frontend.
- [x] **Phase 2**: Map visualization, weather awareness, and Redis caching.
- [x] **Phase 3**: Multi-destination RAG expansion and rule-based reranking.
- [ ] **Next Steps**:
    - Transition to **LangGraph** for more complex agent workflows.
    - Implement **Cross-encoder Reranking** for improved RAG accuracy.
    - Add **GraphRAG** support for interconnected travel entity relationships.
    - Mobile-responsive UI enhancements.

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details. (Note: Check the LICENSE file in the repository for specifics).
