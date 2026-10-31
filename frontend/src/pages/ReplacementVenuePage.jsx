import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import explain from "../utils/explain.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-89: the event's coordinator asks for a replacement for a booking flagged because its
// venue became unavailable (/bookings/:bookingId/replacement). The event and times are fixed
// by the flagged booking; only the venue is chosen. Talks to
// GET/POST /api/venues/bookings/<id>/replacement (backend/app/venues/routes.py). The server
// refuses anyone but the event's coordinator (403) and a booking that is not flagged (409);
// then no form is shown.
const NOT_LOADED = "The replacement search could not be loaded. Check your connection and try again.";
const NOT_SENT = "Your replacement request was not sent. Check your connection and try again.";

// Times are Singapore time without a time zone: show them as recorded.
const asText = (value) => value.slice(0, 16).replace("T", " ");

export default function ReplacementVenuePage() {
  const { bookingId } = useParams();
  const [context, setContext] = useState(null);
  const [venues, setVenues] = useState([]);
  const [freeIds, setFreeIds] = useState(null);
  const [refusal, setRefusal] = useState("");
  const [venueId, setVenueId] = useState("");
  const [suitability, setSuitability] = useState(null);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let current = true;
    (async () => {
      try {
        const { data } = await apiClient.get(`/venues/bookings/${bookingId}/replacement`);
        if (!current) return;
        setContext(data);
        const [all, free] = await Promise.all([
          apiClient.get("/venues/"),
          apiClient.get("/venues/search", { params: {
            date: data.booking.start_time.slice(0, 10),
            start: data.booking.start_time.slice(11, 16),
            end: data.booking.end_time.slice(11, 16),
          } }),
        ]);
        if (!current) return;
        setVenues(all.data.venues);
        setFreeIds(new Set(free.data.venues.map((venue) => venue.id)));
      } catch (failure) {
        if (current) setRefusal(explain(failure, NOT_LOADED));
      }
    })();
    return () => { current = false; };
  }, [bookingId]);

  const choose = async (value) => {
    setVenueId(value);
    setSuitability(null);
    setError("");
    if (!value) return;
    try {
      const { data } = await apiClient.get(`/events/${context.event.id}/venue-suitability`,
        { params: { venue_id: Number(value) } });
      setSuitability(data);
    } catch {
      setSuitability(null);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (!venueId) {
      setError("Select a venue.");
      return;
    }
    setSaving(true);
    try {
      const { data } = await apiClient.post(`/venues/bookings/${bookingId}/replacement`,
        { venue_id: Number(venueId) });
      setSent(data);
    } catch (failure) {
      setError(explain(failure, NOT_SENT));
    } finally {
      setSaving(false);
    }
  };

  if (refusal) return <section><h1>Replacement venue</h1><p role="alert">{refusal}</p></section>;
  if (!context) return <section><h1>Replacement venue</h1><p>Loading...</p></section>;

  const { booking, event } = context;
  return (
    <section>
      <h1>{`Replacement venue for ${event.title}`}</h1>
      <p>{`Replacing: ${booking.venue.name}, ${asText(booking.start_time)} to ${asText(booking.end_time)}`}</p>
      <p>{booking.flag}</p>
      <p>{`Expected attendance: ${event.expected_attendance}`}</p>
      {event.venue_requirements && <p>{`Venue requirements: ${event.venue_requirements}`}</p>}

      {sent ? (
        <div>
          <p role="status">{sent.message}</p>
          <p>{`Venue: ${sent.booking.venue.name}`}</p>
          <p>{`Status: ${statusLabel(sent.booking.status)}`}</p>
          {sent.booking.replaces && (
            <p>{`Replaces booking ${sent.booking.replaces.id} (${sent.booking.replaces.venue.name})`}</p>
          )}
          <Link to={`/events/${event.id}/venue-request`}>Back to venue bookings</Link>
        </div>
      ) : (
        <form onSubmit={submit} noValidate>
          <label>
            Venue
            <select value={venueId} onChange={(e) => choose(e.target.value)}>
              <option value="">Select a venue</option>
              {venues.map((venue) => (
                <option key={venue.id} value={venue.id}>
                  {`${venue.name} (capacity ${venue.capacity}) - ${
                    freeIds && freeIds.has(venue.id) ? "available" : "not available"}`}
                </option>
              ))}
            </select>
          </label>
          {suitability && (
            <div>
              <p>{suitability.summary}</p>
              <ul>
                {suitability.checks.map((check, index) => (
                  <li key={index}>
                    {`${check.label}: ${statusLabel(check.status)} - ${check.detail}`}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {error && <p role="alert">{error}</p>}
          <button type="submit" disabled={saving}>Submit request</button>
        </form>
      )}
    </section>
  );
}
