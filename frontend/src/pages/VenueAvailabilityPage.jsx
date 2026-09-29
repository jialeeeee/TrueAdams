import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import apiClient from "../api/client.js";

// SCRUM-36: view a venue's availability for a date or date range.
// Talks to GET /api/venues/<id>/availability (backend/app/venues/routes.py).

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const STATUS_LABELS = {
  available: "Available",
  unavailable: "Unavailable",
  outside_operating_hours: "Outside operating hours",
  hours_not_recorded: "Operating hours not recorded — confirm with venue staff",
};

const PERIOD_LABELS = { booking: "Confirmed booking", block: "Recorded block" };

// Times are Singapore time with no time zone, so read them as written rather
// than letting the browser convert them.
function parts(iso) {
  const [datePart, timePart = "00:00"] = iso.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  return { year, month, day, time: timePart.slice(0, 5) };
}

export function formatDate(isoDate) {
  const { year, month, day } = parts(isoDate);
  const weekday = DAYS[new Date(year, month - 1, day).getDay()];
  return `${weekday} ${day} ${MONTHS[month - 1]} ${year}`;
}

export function formatDateTime(iso) {
  return `${formatDate(iso)}, ${parts(iso).time}`;
}

// A slot's end is the next midnight when it runs to the end of the day.
function slotTime(iso, date) {
  return iso.startsWith(date) ? parts(iso).time : "24:00";
}

function serverError(failure, fallback) {
  const explanation = failure.response?.data?.error;
  return typeof explanation === "string" && explanation.trim() ? explanation : fallback;
}

export default function VenueAvailabilityPage() {
  const [searchParams] = useSearchParams();
  const [venues, setVenues] = useState([]);
  const [venueId, setVenueId] = useState(searchParams.get("venue") ?? "");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const [calendar, setCalendar] = useState(null);
  const [formError, setFormError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiClient
      .get("/venues/")
      .then((response) => setVenues(response.data.venues))
      .catch((failure) => setFormError(serverError(failure, "Venues could not be loaded.")));
  }, []);

  const load = async () => {
    setLoading(true);
    setLoadError("");
    try {
      const params = to ? { from, to } : { from };
      const response = await apiClient.get(`/venues/${venueId}/availability`, { params });
      setCalendar(response.data);
    } catch (failure) {
      // Never keep showing an old calendar as if it were current (TC-36-30).
      setCalendar(null);
      const status = failure.response?.status;
      const message = serverError(failure, "Availability could not be loaded. Please try again.");
      if (status === 400 || status === 403 || status === 404) {
        setFormError(message);
      } else {
        setLoadError(message);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    setFormError("");
    if (!venueId) {
      setFormError("Select a venue.");
      return;
    }
    if (!from) {
      setFormError("Select a date.");
      return;
    }
    load();
  };

  const venueName = venues.find((v) => String(v.id) === String(calendar?.venue_id))?.name;

  return (
    <section>
      <h1>Venue availability</h1>

      <form onSubmit={handleSubmit} noValidate>
        <label htmlFor="availability-venue">Venue</label>
        <select id="availability-venue" value={venueId} onChange={(e) => setVenueId(e.target.value)}>
          <option value="">Choose a venue</option>
          {venues.map((venue) => (
            <option key={venue.id} value={venue.id}>{venue.name}</option>
          ))}
        </select>

        <label htmlFor="availability-from">From</label>
        <input id="availability-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />

        <label htmlFor="availability-to">To (optional)</label>
        <input id="availability-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />

        <button type="submit" disabled={loading}>View availability</button>
      </form>

      {formError && <p role="alert">{formError}</p>}

      {loadError && (
        <div>
          <p role="alert">{loadError}</p>
          <button type="button" onClick={load}>Retry</button>
        </div>
      )}

      {calendar && (
        <article aria-label="Availability calendar">
          <h2>{venueName ?? "Selected venue"}</h2>
          <button type="button" onClick={load} disabled={loading}>Refresh</button>

          <h3>Bookings and unavailable periods</h3>
          {calendar.periods.length === 0 ? (
            <p>{calendar.message}</p>
          ) : (
            <ul aria-label="Bookings and unavailable periods">
              {calendar.periods.map((period) => (
                <li key={`${period.type}-${period.id}`}>
                  {PERIOD_LABELS[period.type]}: {formatDateTime(period.start)} to{" "}
                  {formatDateTime(period.end)}
                  {period.reason ? ` (${period.reason})` : ""}
                </li>
              ))}
            </ul>
          )}

          {calendar.days.map((day) => (
            <section key={day.date} aria-label={formatDate(day.date)}>
              <h3>{formatDate(day.date)}</h3>
              <ul>
                {day.slots.map((slot) => (
                  <li key={slot.start} data-status={slot.status}>
                    {slotTime(slot.start, day.date)}–{slotTime(slot.end, day.date)}{" "}
                    {STATUS_LABELS[slot.status]}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </article>
      )}
    </section>
  );
}
