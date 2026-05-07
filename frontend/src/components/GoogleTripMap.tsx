import { useEffect, useMemo, useRef, useState } from "react";

interface TripMapPoint {
  key: string;
  dayIndex: number;
  date: string;
  theme: string;
  name: string;
  address: string;
  latitude: number | null | undefined;
  longitude: number | null | undefined;
  poiId: string | null | undefined;
  imageUrl?: string | null;
  description: string;
}

declare global {
  interface Window {
    google?: any;
  }
}

type Props = {
  points: TripMapPoint[];
};

function createInfoWindowContent(point: TripMapPoint): HTMLElement {
  const container = document.createElement("div");
  container.style.maxWidth = "260px";
  container.style.fontFamily = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

  const title = document.createElement("strong");
  title.textContent = point.name;
  container.appendChild(title);
  container.appendChild(document.createElement("br"));

  const meta = document.createElement("span");
  meta.textContent = `${point.dayIndex} · ${point.theme}`;
  container.appendChild(meta);
  container.appendChild(document.createElement("br"));

  const address = document.createElement("span");
  address.textContent = point.address;
  container.appendChild(address);

  return container;
}

export default function GoogleTripMap({ points }: Props) {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapInstance = useRef<any>(null);
  const markers = useRef<any[]>([]);
  const routeLine = useRef<any>(null);
  const [loadError, setLoadError] = useState("");
  const googleKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

  const validPoints = useMemo(
    () => points.filter((point) => point.longitude != null && point.latitude != null),
    [points]
  );

  function clearOverlays() {
    markers.current.forEach((marker) => {
      marker.setMap(null);
    });
    markers.current = [];

    if (routeLine.current) {
      routeLine.current.setMap(null);
      routeLine.current = null;
    }
  }

  function renderMarkers() {
    if (!window.google?.maps || !mapInstance.current) {
      return;
    }

    clearOverlays();
    const sorted = [...validPoints].sort((a, b) => a.dayIndex - b.dayIndex);
    const bounds = new window.google.maps.LatLngBounds();
    const routePath: Array<{ lat: number; lng: number }> = [];

    sorted.forEach((point) => {
      const position = {
        lat: point.latitude as number,
        lng: point.longitude as number,
      };
      bounds.extend(position);
      routePath.push(position);

      const marker = new window.google.maps.Marker({
        position,
        map: mapInstance.current,
        title: point.name,
        label: {
          text: `D${point.dayIndex}`,
          color: "#ffffff",
          fontWeight: "700",
        },
        icon: {
          path: window.google.maps.SymbolPath.CIRCLE,
          fillColor: "#6d82de",
          fillOpacity: 1,
          strokeColor: "#ffffff",
          strokeWeight: 2,
          scale: 9,
        },
      });

      const infoWindow = new window.google.maps.InfoWindow({
        content: createInfoWindowContent(point),
      });

      marker.addListener("click", () => {
        infoWindow.open({ anchor: marker, map: mapInstance.current });
      });

      markers.current.push(marker);
    });

    if (routePath.length >= 2) {
      routeLine.current = new window.google.maps.Polyline({
        path: routePath,
        geodesic: true,
        strokeColor: "#6d82de",
        strokeOpacity: 0.8,
        strokeWeight: 4,
        map: mapInstance.current,
      });
    }

    if (sorted.length === 1) {
      mapInstance.current.setCenter(routePath[0]);
      mapInstance.current.setZoom(13);
    } else if (sorted.length > 1) {
      mapInstance.current.fitBounds(bounds, 80);
    }
  }

  function ensureMapScript(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (window.google?.maps) {
        resolve();
        return;
      }

      const existingScript = document.querySelector<HTMLScriptElement>(
        'script[data-google-maps-loader="true"]'
      );

      if (existingScript) {
        existingScript.addEventListener("load", () => resolve(), { once: true });
        existingScript.addEventListener("error", () => reject(new Error("Google Maps 脚本加载失败。")), {
          once: true,
        });
        return;
      }

      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?key=${googleKey}`;
      script.async = true;
      script.defer = true;
      script.dataset.googleMapsLoader = "true";
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Google Maps load failed"));
      document.head.appendChild(script);
    });
  }

  async function initMap() {
    if (!googleKey) {
      setLoadError("=Google Maps API Key not detected");
      return;
    }

    if (!mapContainer.current) {
      return;
    }

    try {
      setLoadError("");
      await ensureMapScript();

      if (!window.google?.maps) {
        setLoadError("Initialized Google Maps failed");
        return;
      }

      mapInstance.current = new window.google.maps.Map(mapContainer.current, {
        zoom: 11,
        center: validPoints[0]
          ? { lat: validPoints[0].latitude as number, lng: validPoints[0].longitude as number }
          : { lat: 39.9042, lng: 116.4074 },
      });

      renderMarkers();
    } catch (error) {
      console.error(error);
      setLoadError("Load map failed, check Google Maps API Key and network.");
    }
  }

  useEffect(() => {
    void initMap();
    return () => {
      clearOverlays();
      mapInstance.current = null;
    };
  }, [googleKey]);

  useEffect(() => {
    if (mapInstance.current) {
      renderMarkers();
    }
  }, [validPoints]);

  return (
    <div className="trip-map">
      {loadError ? (
        <div className="trip-map__placeholder">
          <strong>Map not loaded</strong>
          <span>{loadError}</span>
        </div>
      ) : validPoints.length === 0 ? (
        <div className="trip-map__placeholder">
          <strong>No points to display</strong>
          <span>Current itinerary has no available latitude and longitude data.</span>
        </div>
      ) : (
        <div ref={mapContainer} className="trip-map__canvas" />
      )}
    </div>
  );
}
