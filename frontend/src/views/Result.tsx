import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import GoogleTripMap from "../components/GoogleTripMap";
import {
  editTrip,
  fetchWeatherForecast,
  getMarkdownExportUrl,
  getPdfExportUrl,
  saveTrip,
} from "../services/api";
import type { Itinerary, WeatherForecastResponse } from "../types";

type Props = {
  itinerary: Itinerary | null;
  onBackHome: () => void;
  onViewHistory: () => void;
  onUpdated: (itinerary: Itinerary) => void;
};

const technicalTipKeywords = [
  "LLM",
  "RAG",
  "LangChain",
  "Chroma",
  "Demonstration",
  "Test",
  "Rules",
  "Modules",
  "Source Code",
];
const rainWeatherKeywords = ["Rainy", "Showers", "Thunder Showers", "Light Rain", "Moderate Rain", "Heavy Rain"];
const sunnyTipKeywords = ["Sunscreen", "Sun", "Sunlight", "Sunny"];

function formatShortDate(dateText?: string | null): string {
  if (!dateText) {
    return "Undecided";
  }
  const parts = dateText.split("-");
  if (parts.length !== 3) {
    return dateText;
  }
  return `${parts[1]}-${parts[2]}`;
}

function formatWeatherDate(dateText?: string | null, week?: string | null): string {
  const weekdayMap: Record<string, string> = {
    "1": "Monday",
    "2": "Tuesday",
    "3": "Wednesday",
    "4": "Thursday",
    "5": "Friday",
    "6": "Saturday",
    "7": "Sunday",
  };
  const weekday = week ? weekdayMap[week] || `Week ${week}` : "";
  return [formatShortDate(dateText), weekday].filter(Boolean).join(" ");
}

export default function Result({ itinerary, onBackHome, onViewHistory, onUpdated }: Props) {
  const [saving, setSaving] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportingMarkdown, setExportingMarkdown] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editScope, setEditScope] = useState("day_1");
  const [editInstruction, setEditInstruction] = useState(
    "Easier this day, fewer fixed plans. Change to a place good for sunset."
  );
  const [weatherLoading, setWeatherLoading] = useState(false);
  const [weatherError, setWeatherError] = useState("");
  const [weather, setWeather] = useState<WeatherForecastResponse | null>(null);

  useEffect(() => {
    if (itinerary?.trip_id) {
      const firstDayIndex = itinerary.days[0]?.day_index ?? 1;
      setEditScope(`day_${firstDayIndex}`);
    }
  }, [itinerary?.trip_id]);

  useEffect(() => {
    const destination = itinerary?.destination;
    if (!destination) {
      setWeather(null);
      return;
    }
    const city = destination;

    let cancelled = false;
    async function loadWeather() {
      setWeatherLoading(true);
      setWeatherError("");
      try {
        const response = await fetchWeatherForecast(city);
        if (!cancelled) {
          setWeather(response);
        }
      } catch (error) {
        console.error(error);
        if (!cancelled) {
          setWeather(null);
          setWeatherError("Failed to load weather.");
        }
      } finally {
        if (!cancelled) {
          setWeatherLoading(false);
        }
      }
    }

    void loadWeather();
    return () => {
      cancelled = true;
    };
  }, [itinerary?.destination]);

  const budgetItems = useMemo(() => {
    if (!itinerary) {
      return [];
    }
    const budget = itinerary.budget_breakdown;
    return [
      { label: "Attraction Tickets", value: `$${budget.tickets.toFixed(0)}` },
      { label: "Accommodation", value: `$${budget.hotel.toFixed(0)}` },
      { label: "Meals", value: `$${budget.meals.toFixed(0)}` },
      { label: "Transportation", value: `$${budget.transport.toFixed(0)}` },
    ];
  }, [itinerary]);

  const dayBudgetItems = useMemo(() => {
    if (!itinerary) {
      return [];
    }
    return itinerary.days.map((day) => {
      const tickets = day.spots.reduce((sum, spot) => sum + (spot.estimated_cost ?? 0), 0);
      const meals = day.meals.reduce((sum, meal) => sum + (meal.estimated_cost ?? 0), 0);
      const transport = day.transport.reduce((sum, item) => sum + (item.estimated_cost ?? 0), 0);
      const hotel = day.hotel?.estimated_cost ?? 0;
      const total = tickets + meals + transport + hotel;

      return {
        key: day.day_index,
        title: `Day ${day.day_index} days`,
        subtitle: day.theme || "Unnamed Theme",
        tickets,
        meals,
        transport,
        hotel,
        total,
      };
    });
  }, [itinerary]);

  const mapPoints = useMemo(() => {
    if (!itinerary) {
      return [];
    }
    return itinerary.days.flatMap((day) =>
      day.spots.map((spot) => ({
        key: `${day.day_index}-${spot.name}`,
        dayIndex: day.day_index,
        date: day.date || "Undecided",
        theme: day.theme || "Unnamed Theme",
        name: spot.name,
        address: spot.address || spot.location || "Undecided",
        latitude: spot.latitude,
        longitude: spot.longitude,
        poiId: spot.poi_id,
        imageUrl: spot.image_url,
        description: spot.description || "No description available",
      }))
    );
  }, [itinerary]);

  const weatherText = useMemo(() => {
    if (!weather) {
      return "";
    }
    return weather.days.map((day) => `${day.day_weather || ""}${day.night_weather || ""}`).join(" ");
  }, [weather]);

  const hasRainyWeather = useMemo(() => {
    return rainWeatherKeywords.some((keyword) => weatherText.includes(keyword));
  }, [weatherText]);

  const displayTips = useMemo(() => {
    if (!itinerary) {
      return [];
    }

    const tips = itinerary.tips
      .map((tip) => tip.trim())
      .filter(Boolean)
      .filter((tip) => !technicalTipKeywords.some((keyword) => tip.includes(keyword)));

    const weatherAwareTips = hasRainyWeather
      ? tips.filter((tip) => !sunnyTipKeywords.some((keyword) => tip.includes(keyword)))
      : tips;

    if (hasRainyWeather) {
      weatherAwareTips.push("Weather may be rainy, consider carrying an umbrella or lightweight raincoat.");
      weatherAwareTips.push("Wet roads can be slippery, recommend wearing anti-slip shoes near Lake and old town stone paths.");
    }

    const uniqueTips = Array.from(new Set(weatherAwareTips));
    if (uniqueTips.length) {
      return uniqueTips;
    }

    return [
      `Considering${itinerary.destination} to prepare raincoat and umbrella`,
      "Old towns, ecological corridors, and stone paths are better for slow walking; try to choose comfortable and anti-slip shoes.",
    ];
  }, [hasRainyWeather, itinerary]);

  function buildVisibleItinerary(): Itinerary | null {
    if (!itinerary) {
      return null;
    }
    return {
      ...itinerary,
      tips: displayTips,
    };
  }

  async function openPdfExport() {
    const itineraryToExport = buildVisibleItinerary();
    if (!itineraryToExport) {
      return;
    }

    const exportWindow = window.open("about:blank", "_blank");
    setExportingPdf(true);
    try {
      await saveTrip(itineraryToExport);
      const exportUrl = getPdfExportUrl(itineraryToExport.trip_id);
      if (exportWindow) {
        exportWindow.location.href = exportUrl;
      } else {
        window.location.href = exportUrl;
      }
    } catch (error) {
      console.error(error);
      exportWindow?.close();
      toast.error("Failed to synchronize current itinerary before exporting PDF.");
    } finally {
      setExportingPdf(false);
    }
  }

  async function openMarkdownExport() {
    const itineraryToExport = buildVisibleItinerary();
    if (!itineraryToExport) {
      return;
    }

    const exportWindow = window.open("about:blank", "_blank");
    setExportingMarkdown(true);
    try {
      await saveTrip(itineraryToExport);
      const exportUrl = getMarkdownExportUrl(itineraryToExport.trip_id);
      if (exportWindow) {
        exportWindow.location.href = exportUrl;
      } else {
        window.location.href = exportUrl;
      }
    } catch (error) {
      console.error(error);
      exportWindow?.close();
      toast.error("Failed to synchronize current itinerary before exporting Markdown.");
    } finally {
      setExportingMarkdown(false);
    }
  }

  async function handleSave() {
    const itineraryToSave = buildVisibleItinerary();
    if (!itineraryToSave) {
      return;
    }

    setSaving(true);
    try {
      await saveTrip(itineraryToSave);
      toast.success("Itinerary has been saved and can be viewed in the history list.");
    } catch (error) {
      console.error(error);
      toast.error("Failed to save itinerary.");
    } finally {
      setSaving(false);
    }
  }

  async function handleEdit() {
    if (!itinerary) {
      return;
    }

    const instruction = editInstruction.trim();
    if (!instruction) {
      toast.warning("Please enter your adjustment instructions.");
      return;
    }

    setEditing(true);
    try {
      const updatedItinerary = await editTrip({
        trip_id: itinerary.trip_id,
        current_itinerary: itinerary,
        user_instruction: instruction,
        edit_scope: editScope,
        preserve_constraints: ["Save budget structure", "Save destinations and dates"],
      });
      onUpdated(updatedItinerary);
      toast.success("Itinerary has been adjusted.");
    } catch (error) {
      console.error(error);
      toast.error("Failed to adjust itinerary, please try again.");
    } finally {
      setEditing(false);
    }
  }

  if (!itinerary) {
    return (
      <div className="flex items-center justify-center min-h-400">
        <Card className="w-full max-w-md">
          <CardContent className="text-center p-6">
            <h2 className="text-xl font-semibold mb-2">Results not generated yet</h2>
            <p className="text-gray-600 mb-4">Generate one itinerary in the plan page, the result page will display the real data.</p>
            <Button onClick={onBackHome}>Return the plan page</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex gap-6">
      <aside className="w-64 shrink-0">
        <Card>
          <CardHeader>
            <CardTitle>Itinerary Guide</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              <li>Overview</li>
              <li>Budget Details</li>
              <li>Daily Expenses</li>
              <li>Smart Adjustments</li>
              <li>Attraction Map</li>
              <li>Weather Information</li>
              <li>Location Details</li>
              <li>Daily Itinerary</li>
            </ul>
            <div className="mt-6 space-y-2">
              <Button variant="outline" onClick={onBackHome} className="w-full">
                Return to Plan Page
              </Button>
              <Button disabled={saving} onClick={handleSave} className="w-full">
                {saving ? "Saving..." : "Save Itinerary"}
              </Button>
              <Button variant="outline" onClick={onViewHistory} className="w-full">
                History List
              </Button>
              <Button disabled={exportingPdf} onClick={openPdfExport} className="w-full">
                {exportingPdf ? "Preparing PDF..." : "Export PDF"}
              </Button>
              <Button variant="outline" disabled={exportingMarkdown} onClick={openMarkdownExport} className="w-full">
                {exportingMarkdown ? "Preparing..." : "Export Markdown"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </aside>

      <main className="flex-1 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{itinerary.destination} Travel Plan</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div><strong>Itinerary ID:</strong>{itinerary.trip_id}</div>
            <div><strong>Dates:</strong>{itinerary.days[0]?.date || "TBD"} to {itinerary.days[itinerary.days.length - 1]?.date || "TBD"}</div>
            <div><strong>Destination:</strong>{itinerary.destination}</div>
            <div className="text-sm text-gray-700">{itinerary.summary}</div>
            {displayTips.length > 0 && (
              <div>
                <h4 className="font-semibold mb-2">Travel Tips</h4>
                <ul className="list-disc list-inside space-y-1 text-sm">
                  {displayTips.map((tip) => (
                    <li key={tip}>{tip}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Budget Details</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 mb-4">
              {budgetItems.map((item) => (
                <div key={item.label} className="text-center p-4 bg-gray-50 rounded-lg">
                  <div className="text-sm text-gray-600">{item.label}</div>
                  <div className="text-lg font-semibold">{item.value}</div>
                </div>
              ))}
            </div>
            <div className="text-center p-4 bg-blue-50 rounded-lg">
              <span className="text-sm text-gray-600">Estimated Total Cost</span>
              <div className="text-xl font-bold text-blue-600">${itinerary.estimated_budget.toFixed(0)}</div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Attraction Map</CardTitle>
          </CardHeader>
          <CardContent>
            <GoogleTripMap points={mapPoints} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Weather Information</CardTitle>
          </CardHeader>
          <CardContent>
            {weatherLoading ? (
              <div className="text-center py-4">Loading weather information...</div>
            ) : weatherError ? (
              <div className="text-center py-4 text-red-600">{weatherError}</div>
            ) : weather ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {weather.days.map((day) => (
                  <div key={`${day.date}-${day.week}`} className="p-4 border rounded-lg text-center">
                    <div className="font-semibold">{formatWeatherDate(day.date, day.week)}</div>
                    <div className="text-lg">{day.day_temp || "-"}° / {day.night_temp || "-"}°</div>
                    <div className="text-sm text-gray-600">Daytime: {day.day_weather || "Unknown"}</div>
                    <div className="text-sm text-gray-600">Night: {day.night_weather || "Unknown"}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-4">No weather information available.</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Intelligent Itinerary Adjustment</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-4 items-end">
              <div className="flex-1">
                <label className="block text-sm font-medium mb-2">Adjustment Range</label>
                <Select value={editScope} onValueChange={setEditScope}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {itinerary.days.map((day) => (
                      <SelectItem key={day.day_index} value={`day_${day.day_index}`}>
                        Day {day.day_index} · {day.theme || "Unnamed Theme"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button disabled={editing} onClick={handleEdit}>
                {editing ? "Adjusting..." : "Intelligent Adjustment"}
              </Button>
            </div>
            <Textarea
              value={editInstruction}
              rows={3}
              placeholder="Example: Easier 2nd day, fewer fixed plans. Change to a place good for sunset 3rd day."
              onChange={(event) => setEditInstruction(event.target.value)}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Day-by-Day Expenses</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {dayBudgetItems.map((item) => (
                <div key={item.key} className="p-4 border rounded-lg">
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-semibold">{item.title}</span>
                    <span className="text-sm text-gray-600">{item.subtitle}</span>
                  </div>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span>Tickets</span>
                      <strong>${item.tickets.toFixed(0)}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Meals</span>
                      <strong>${item.meals.toFixed(0)}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Transportation</span>
                      <strong>${item.transport.toFixed(0)}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Hotel</span>
                      <strong>${item.hotel.toFixed(0)}</strong>
                    </div>
                    <div className="flex justify-between border-t pt-1">
                      <span>Day Total</span>
                      <strong>${item.total.toFixed(0)}</strong>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Map Point Details</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {mapPoints.map((point) => (
                <div key={point.key} className="border rounded-lg p-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-semibold">Day {point.dayIndex} · {point.name}</span>
                    <span className="text-sm text-gray-600">{formatShortDate(point.date)}</span>
                  </div>
                  {point.imageUrl ? (
                    <div
                      className="w-full h-32 bg-cover bg-center rounded mb-2"
                      style={{ backgroundImage: `url(${point.imageUrl})` }}
                    />
                  ) : (
                    <div className="w-full h-32 bg-gray-200 rounded mb-2 flex items-center justify-center text-sm text-gray-500">
                      No Scenic Spot Images Available
                    </div>
                  )}
                  <div className="space-y-1 text-sm">
                    <div><strong>Theme: </strong>{point.theme}</div>
                    <div><strong>Address: </strong>{point.address}</div>
                    <div className="text-gray-700">{point.description}</div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Daily Itinerary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {itinerary.days.map((day) => (
                <details key={day.day_index} className="border rounded-lg p-4" open={day.day_index === 1}>
                  <summary className="cursor-pointer font-semibold flex justify-between items-center">
                    <span>Day {day.day_index} · {day.theme || "Unnamed Theme"}</span>
                    <span className="text-sm text-gray-600">{formatShortDate(day.date)}</span>
                  </summary>
                  <div className="mt-4 space-y-2 text-sm">
                    <div><strong>Main spots: </strong>{day.spots[0]?.name || "Undecided"}</div>
                    <div><strong>Address: </strong>{day.spots[0]?.address || day.spots[0]?.location || "Undecided"}</div>
                    <div><strong>Meals: </strong>{day.meals[0]?.name || "Undecided"}</div>
                    <div><strong>Hotel: </strong>{day.hotel?.name || "Undecided"}</div>
                    <div><strong>Transportation: </strong>
                      {day.transport[0]?.distance_km != null
                        ? `${day.transport[0].distance_km.toFixed(2)} km / ${day.transport[0].estimated_minutes ?? 0} minute`
                        : day.transport[0]?.duration || "Undecided"}
                    </div>
                    <div><strong>Notes: </strong>{day.notes[day.notes.length - 1] || "Blank"}</div>
                  </div>
                </details>
              ))}
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
