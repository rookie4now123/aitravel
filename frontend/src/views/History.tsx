import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { deleteTrip, getTripDetail, listTrips } from "../services/api";
import type { Itinerary, TripSummaryItem } from "../types";

type Props = {
  active: boolean;
  onOpenTrip: (itinerary: Itinerary) => void;
};

export default function History({ active, onOpenTrip }: Props) {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<TripSummaryItem[]>([]);
  const [deletingTripId, setDeletingTripId] = useState("");

  async function loadTrips() {
    setLoading(true);
    try {
      const response = await listTrips();
      setItems(response.items);
    } catch (error) {
      console.error(error);
      toast.error("Failed to load history list.");
    } finally {
      setLoading(false);
    }
  }

  async function openTrip(tripId: string) {
    try {
      const response = await getTripDetail(tripId);
      onOpenTrip(response.itinerary);
      toast.success("Failed to load history list.");
    } catch (error) {
      console.error(error);
      toast.error("Failed to read trip details.");
    }
  }

  async function removeTrip(tripId: string) {
    const confirmed = window.confirm("Deleted trips cannot be recovered.");
    if (!confirmed) {
      return;
    }

    setDeletingTripId(tripId);
    try {
      await deleteTrip(tripId);
      setItems((prev) => prev.filter((item) => item.trip_id !== tripId));
      toast.success("History list deleted.");
    } catch (error) {
      console.error(error);
      toast.error("Failed to delete trip.");
    } finally {
      setDeletingTripId("");
    }
  }

  useEffect(() => {
    if (active) {
      void loadTrips();
    }
  }, [active]);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">History Trip</h2>
          <p className="text-gray-600">Itinerary summary stored in database displays here.</p>
        </div>
        <Button onClick={loadTrips}>Refresh List</Button>
      </div>

      {loading ? (
        <div className="text-center py-8">Loading history list...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-8">No saved trips available.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {items.map((item) => (
            <Card key={item.trip_id}>
              <CardHeader>
                <CardTitle>{item.destination}</CardTitle>
                <p className="text-sm text-gray-500">{item.trip_id}</p>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm">{item.summary}</p>
                <p className="text-xs text-gray-500">Updated at: {item.updated_at || "Not recorded"}</p>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => openTrip(item.trip_id)}>
                    View Details
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={deletingTripId === item.trip_id}
                    onClick={() => removeTrip(item.trip_id)}
                  >
                    {deletingTripId === item.trip_id ? "Deleting..." : "Delete Trip"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
