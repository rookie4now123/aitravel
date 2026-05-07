import { useEffect, useState } from "react";
import type { Itinerary } from "./types";
import { Button } from "@/components/ui/button";
import { getTripDetail } from "./services/api";
import Home from "./views/Home";
import Result from "./views/Result";
import History from "./views/History";

type PageView = "home" | "result" | "history";

type RouteState = {
  view: PageView;
  tripId: string | null;
};

const viewValues: PageView[] = ["home", "result", "history"];
const canUseBrowser = typeof window !== "undefined";

function readRouteState(): RouteState {
  if (!canUseBrowser) {
    return {
      view: "home",
      tripId: null,
    };
  }

  const params = new URLSearchParams(window.location.search);
  const requestedView = params.get("view");
  const view = viewValues.includes(requestedView as PageView)
    ? (requestedView as PageView)
    : "home";

  return {
    view,
    tripId: params.get("trip_id"),
  };
}

function writeRouteState(view: PageView, tripId?: string | null) {
  if (!canUseBrowser) {
    return;
  }

  const url = new URL(window.location.href);

  if (view === "home") {
    url.searchParams.delete("view");
    url.searchParams.delete("trip_id");
  } else {
    url.searchParams.set("view", view);
    if (view === "result" && tripId) {
      url.searchParams.set("trip_id", tripId);
    } else {
      url.searchParams.delete("trip_id");
    }
  }

  window.history.pushState({}, "", url);
}

function cacheItinerary(itinerary: Itinerary) {
  if (!canUseBrowser) {
    return;
  }

  try {
    sessionStorage.setItem(`trip:${itinerary.trip_id}`, JSON.stringify(itinerary));
  } catch (error) {
    console.warn("Unable to cache itinerary in sessionStorage", error);
  }
}

function readCachedItinerary(tripId: string): Itinerary | null {
  if (!canUseBrowser) {
    return null;
  }

  try {
    const cached = sessionStorage.getItem(`trip:${tripId}`);
    return cached ? (JSON.parse(cached) as Itinerary) : null;
  } catch (error) {
    console.warn("Unable to read cached itinerary from sessionStorage", error);
    return null;
  }
}

function App() {
  const [currentView, setCurrentView] = useState<PageView>("home");
  const [routeTripId, setRouteTripId] = useState<string | null>(null);
  const [latestItinerary, setLatestItinerary] = useState<Itinerary | null>(null);
  const [routeLoading, setRouteLoading] = useState(false);
  const [routeError, setRouteError] = useState("");

  function showHome() {
    setCurrentView("home");
    setRouteTripId(null);
    setRouteError("");
    writeRouteState("home");
  }

  function showHistory() {
    setCurrentView("history");
    setRouteTripId(null);
    setRouteError("");
    writeRouteState("history");
  }

  function showResult(itinerary: Itinerary) {
    cacheItinerary(itinerary);
    setLatestItinerary(itinerary);
    setCurrentView("result");
    setRouteTripId(itinerary.trip_id);
    setRouteError("");
    writeRouteState("result", itinerary.trip_id);
  }

  function handleGenerated(itinerary: Itinerary) {
    showResult(itinerary);
  }

  function openTrip(itinerary: Itinerary) {
    showResult(itinerary);
  }

  function updateCurrentItinerary(itinerary: Itinerary) {
    showResult(itinerary);
  }

  useEffect(() => {
    function handlePopState() {
      const nextRoute = readRouteState();
      setCurrentView(nextRoute.view);
      setRouteTripId(nextRoute.tripId);
      setRouteError("");
    }

    handlePopState();
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (currentView !== "result" || !routeTripId) {
      return;
    }

    if (latestItinerary?.trip_id === routeTripId) {
      return;
    }

    const tripId = routeTripId;
    const cached = readCachedItinerary(tripId);
    if (cached) {
      setLatestItinerary(cached);
    }

    let cancelled = false;
    async function loadRouteTrip() {
      setRouteLoading(true);
      setRouteError("");
      try {
        const response = await getTripDetail(tripId);
        if (!cancelled) {
          setLatestItinerary(response.itinerary);
          cacheItinerary(response.itinerary);
        }
      } catch (error) {
        console.error(error);
        if (!cancelled && !cached) {
          setLatestItinerary(null);
          setRouteError("Unable to load this itinerary from link, please open the saved trip in history list first.");
        }
      } finally {
        if (!cancelled) {
          setRouteLoading(false);
        }
      }
    }

    void loadRouteTrip();
    return () => {
      cancelled = true;
    };
  }, [currentView, latestItinerary?.trip_id, routeTripId]);

  return (
    <div className="relative min-h-screen p-10 pb-16 overflow-hidden">
      <div className="absolute w-80 h-80 rounded-full blur-xl opacity-50 pointer-events-none -top-27.5 -left-27.5 bg-blue-200" />
      <div className="absolute w-80 h-80 rounded-full blur-xl opacity-50 pointer-events-none -top-27.5 -right-27.5 bg-purple-200" />

      <header className="text-center mb-8">
        <div className="inline-block px-3 py-1 text-sm font-medium bg-blue-100 text-blue-800 rounded-full mb-4">
          Trip Planner Demo
        </div>
        <h1 className="text-4xl font-bold text-gray-900 mb-6">Travel Assistant</h1>

        <div className="flex justify-center space-x-4">
          <Button
            variant={currentView === "home" ? "default" : "outline"}
            onClick={showHome}
          >
            Plan Page
          </Button>
          <Button
            variant={currentView === "result" ? "default" : "outline"}
            disabled={!latestItinerary && !routeTripId}
            onClick={() => {
              if (latestItinerary) {
                showResult(latestItinerary);
              }
            }}
          >
            Result Page
          </Button>
          <Button
            variant={currentView === "history" ? "default" : "outline"}
            onClick={showHistory}
          >
            History Page
          </Button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto">
        {currentView === "home" && <Home onGenerated={handleGenerated} />}
        {currentView === "result" && routeLoading && (
          <div className="mb-4 rounded-md border border-input bg-background px-4 py-3 text-sm text-muted-foreground">
            Loading itinerary from link...
          </div>
        )}
        {currentView === "result" && routeError && (
          <div className="mb-4 rounded-md border border-destructive bg-background px-4 py-3 text-sm text-destructive">
            {routeError}
          </div>
        )}
        {currentView === "result" && (
          <Result
            itinerary={latestItinerary}
            onBackHome={showHome}
            onViewHistory={showHistory}
            onUpdated={updateCurrentItinerary}
          />
        )}
        {currentView === "history" && <History active onOpenTrip={openTrip} />}
      </main>
    </div>
  );
}

export default App;
