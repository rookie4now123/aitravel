import { useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import axios from "axios";
import { generateTrip } from "../services/api";
import type { Itinerary, TripRequestPayload } from "../types";

const preferenceOptions = ["Scenic Spot", "Photo", "Food", "Old Town", "Entertainment"];
const dietaryOptions = ["Less Spicy", "No Celery", "No Green Onions"];

function formatDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

type Props = {
  onGenerated: (itinerary: Itinerary) => void;
};

const initialToday = new Date();
const initialEnd = new Date(initialToday);
initialEnd.setDate(initialEnd.getDate() + 2);

const defaultFormState = {
  destination: "Krakow",
  startDate: formatDate(initialToday),
  endDate: formatDate(initialEnd),
  travelers: 2,
  budget: 3200,
  hotelLevel: "Star-3",
  pace: "Relax",
  preferences: ["Scenic Spot", "Photo", "Food"],
  dietaryPreferences: ["Less Spicy"],
  notes: "Don't want to wake up too early, hope to arrange a place suitable for sunset.",
};

type FormState = typeof defaultFormState;

export default function Home({ onGenerated }: Props) {
  const [formState, setFormState] = useState<FormState>(defaultFormState);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const dayCount = useMemo(() => {
    const start = new Date(formState.startDate);
    const end = new Date(formState.endDate);
    const diff = end.getTime() - start.getTime();
    if (Number.isNaN(diff)) {
      return 0;
    }
    return Math.max(Math.floor(diff / 86400000) + 1, 0);
  }, [formState.startDate, formState.endDate]);

  function updateField<TField extends keyof FormState>(field: TField, value: FormState[TField]) {
    setFormState((prev: FormState) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit() {
    const payload: TripRequestPayload = {
      destination: formState.destination,
      start_date: formState.startDate,
      end_date: formState.endDate,
      travelers: formState.travelers,
      budget: formState.budget,
      preferences: formState.preferences,
      pace: formState.pace,
      dietary_preferences: formState.dietaryPreferences,
      hotel_level: formState.hotelLevel,
      special_notes: formState.notes,
    };

    setIsSubmitting(true);
    try {
      const itinerary = await generateTrip(payload);
      toast.success("Itinerary generated successfully, switched to result page.");
      onGenerated(itinerary);
    } catch (error: unknown) {
      console.error(error);
      const axiosError = axios.isAxiosError(error) ? error : null;
      if (axiosError) {
        if (axiosError.code === "ECONNABORTED") {
          toast.error("Itinerary generation timed out, model response is slow, please try again later.");
        } else if (axiosError.response) {
          toast.error(`Itinerary generation failed: Backend returned ${axiosError.response.status}.`);
        } else {
          toast.error("Itinerary generation failed, please check the connection from frontend to backend.");
        }
      } else {
        toast.error("Itinerary generation failed, please check the connection from frontend to backend.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>📍</span>
            Destination and Dates
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
            <div className="md:col-span-3">
              <label className="block text-sm font-medium mb-2">Destination City</label>
              <Input
                value={formState.destination}
                placeholder="Please enter the destination"
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  updateField("destination", event.target.value)
                }
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium mb-2">Start Date</label>
              <Input
                type="date"
                value={formState.startDate}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  updateField("startDate", event.target.value)
                }
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium mb-2">End Date</label>
              <Input
                type="date"
                value={formState.endDate}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  updateField("endDate", event.target.value)
                }
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium mb-2">Number of Travelers</label>
              <Input
                type="number"
                min={1}
                value={formState.travelers}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  updateField("travelers", Number(event.target.value) || 1)
                }
              />
            </div>
            <div className="md:col-span-3">
              <label className="block text-sm font-medium mb-2">Number of Travel Days</label>
              <div className="flex items-center justify-center h-10 px-3 py-2 bg-gray-100 rounded-md text-sm">
                {dayCount} days
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>⚙️</span>
            Preference
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">Pace Preference</label>
              <Select value={formState.pace} onValueChange={(value) => updateField("pace", value)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="relaxed">Relaxed</SelectItem>
                  <SelectItem value="moderate">Moderate</SelectItem>
                  <SelectItem value="fast-paced">Fast-paced</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Accommodation Preference</label>
              <Select value={formState.hotelLevel} onValueChange={(value) => updateField("hotelLevel", value)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Comfortable">Comfortable</SelectItem>
                  <SelectItem value="Premium">Premium</SelectItem>
                  <SelectItem value="Economy">Economy</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Budget</label>
              <Input
                type="number"
                min={0}
                value={formState.budget}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  updateField("budget", Number(event.target.value) || 0)
                }
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Travel Preferences</label>
            <div className="flex flex-wrap gap-4">
              {preferenceOptions.map((option) => (
                <div key={option} className="flex items-center space-x-2">
                  <Checkbox
                    id={option}
                    checked={formState.preferences.includes(option)}
                    onCheckedChange={(checked) => {
                      if (checked) {
                        updateField("preferences", [...formState.preferences, option]);
                      } else {
                        updateField("preferences", formState.preferences.filter((p) => p !== option));
                      }
                    }}
                  />
                  <label htmlFor={option} className="text-sm">{option}</label>
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Dietary Preferences</label>
            <div className="flex flex-wrap gap-4">
              {dietaryOptions.map((option) => (
                <div key={option} className="flex items-center space-x-2">
                  <Checkbox
                    id={option}
                    checked={formState.dietaryPreferences.includes(option)}
                    onCheckedChange={(checked) => {
                      if (checked) {
                        updateField("dietaryPreferences", [...formState.dietaryPreferences, option]);
                      } else {
                        updateField("dietaryPreferences", formState.dietaryPreferences.filter((p) => p !== option));
                      }
                    }}
                  />
                  <label htmlFor={option} className="text-sm">{option}</label>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>💬</span>
            Additional Requirements
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={formState.notes}
            rows={4}
            placeholder="Enter any additional requirements or notes"
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
              updateField("notes", event.target.value)
            }
          />
          <Button onClick={handleSubmit} disabled={isSubmitting} className="w-full">
            {isSubmitting ? "Generating..." : "Start Planning"}
          </Button>
          <div className="text-sm text-gray-500">
            Currently connected to `/trip/generate`, the generated itinerary will be displayed directly upon successful generation.
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
