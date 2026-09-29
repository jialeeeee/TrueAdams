import { useState } from "react";
import apiClient from "../api/client.js";

// SCRUM-37: search for available venues using an event's requirements.
// Talks to GET /api/venues/search (backend/app/venues/routes.py).

// Must match SUPPORTED_LAYOUTS in backend/app/venues/routes.py.
const LAYOUTS = [
  ["theatre", "Theatre"], ["banquet", "Banquet"], ["cabaret", "Cabaret"],
  ["cocktail", "Cocktail"], ["classroom", "Classroom"], ["boardroom", "Boardroom"],
  ["u_shape", "U-shape"],
];

const EMPTY_FILTERS = {
  date: "", start: "", end: "", minCapacity: "", location: "",
  accessibility: "", layout: "", facilities: "",
};

// "Projector, Wi-Fi" -> ["Projector", "Wi-Fi"]
function splitList(text) {
  return text.split(",").map((item) => item.trim()).filter(Boolean);
}

// Repeated keys (facility=a&facility=b), as the API expects for multiple values.
export function searchParams(filters) {
  const params = new URLSearchParams();
  if (filters.date) params.append("date", filters.date);
  if (filters.start) params.append("start", filters.start);
  if (filters.end) params.append("end", filters.end);
  if (filters.minCapacity.trim()) params.append("min_capacity", filters.minCapacity.trim());
  if (filters.location.trim()) params.append("location", filters.location.trim());
  splitList(filters.accessibility).forEach((need) => params.append("accessibility", need));
  if (filters.layout) params.append("layout", filters.layout);
  splitList(filters.facilities).forEach((facility) => params.append("facility", facility));
  return params;
}

function serverError(failure, fallback) {
  const explanation = failure.response?.data?.error;
  return typeof explanation === "string" && explanation.trim() ? explanation : fallback;
}

function matchedText(matches) {
  return Object.values(matches).flat().join(", ");
}

function VenueResult({ venue }) {
  const [details, setDetails] = useState(null);
  const [detailsError, setDetailsError] = useState("");

  const showDetails = async () => {
    setDetailsError("");
    try {
      // details_url starts with /api, which the client's base URL already adds.
      const response = await apiClient.get(venue.details_url.replace(/^\/api/, ""));
      setDetails(response.data);
    } catch (failure) {
      setDetailsError(serverError(failure, "Venue details could not be loaded."));
    }
  };

  const matched = matchedText(venue.matches);

  return (
    <li aria-label={venue.name}>
      <h3>{venue.name}</h3>
      <p>Location: {venue.location ?? "Not recorded"}</p>
      <p>Capacity: {venue.capacity ?? "Not recorded"}</p>
      {matched && <p>Matches: {matched}</p>}
      {details ? (
        <dl aria-label={`${venue.name} details`}>
          <dt>Description</dt><dd>{details.description ?? "Not recorded"}</dd>
          <dt>Facilities</dt><dd>{details.facilities?.join(", ") || "Not recorded"}</dd>
          <dt>Accessibility</dt>
          <dd>{details.accessibility_features?.join(", ") || "Not recorded"}</dd>
          <dt>Layouts</dt><dd>{details.room_layouts?.join(", ") || "Not recorded"}</dd>
          <dt>Operating hours</dt><dd>{details.operating_hours ?? "Not recorded"}</dd>
        </dl>
      ) : (
        <button type="button" onClick={showDetails}>View details</button>
      )}
      {detailsError && <p role="alert">{detailsError}</p>}
    </li>
  );
}

export default function VenueSearchPage() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [results, setResults] = useState(null);
  const [formError, setFormError] = useState("");
  const [searchError, setSearchError] = useState("");
  const [searching, setSearching] = useState(false);

  const change = (field) => (event) => setFilters({ ...filters, [field]: event.target.value });

  const search = async () => {
    setSearching(true);
    setFormError("");
    setSearchError("");
    try {
      const response = await apiClient.get("/venues/search", { params: searchParams(filters) });
      setResults(response.data);
    } catch (failure) {
      // A failed search must never look like "no matching venues" (TC-37-32).
      setResults(null);
      const status = failure.response?.status;
      const message = serverError(failure, "The venue search could not be completed. Please try again.");
      if (status === 400 || status === 403) {
        setFormError(message);
      } else {
        setSearchError(message);
      }
    } finally {
      setSearching(false);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    search();
  };

  const clear = () => {
    setFilters(EMPTY_FILTERS);
    setResults(null);
    setFormError("");
    setSearchError("");
  };

  return (
    <section>
      <h1>Search for available venues</h1>

      {/* Filters stay filled in after a search, so they can be revised (TC-37-30). */}
      <form onSubmit={handleSubmit} noValidate>
        <fieldset>
          <legend>When</legend>
          <label htmlFor="search-date">Date</label>
          <input id="search-date" type="date" value={filters.date} onChange={change("date")} />
          <label htmlFor="search-start">Start time</label>
          <input id="search-start" type="time" value={filters.start} onChange={change("start")} />
          <label htmlFor="search-end">End time</label>
          <input id="search-end" type="time" value={filters.end} onChange={change("end")} />
        </fieldset>

        <label htmlFor="search-capacity">Minimum capacity</label>
        <input id="search-capacity" type="number" min="1" step="1" value={filters.minCapacity}
          onChange={change("minCapacity")} />

        <label htmlFor="search-location">Location</label>
        <input id="search-location" type="text" value={filters.location} onChange={change("location")} />

        <label htmlFor="search-accessibility">Accessibility needs (comma-separated)</label>
        <input id="search-accessibility" type="text" value={filters.accessibility}
          onChange={change("accessibility")} />

        <label htmlFor="search-layout">Layout</label>
        <select id="search-layout" value={filters.layout} onChange={change("layout")}>
          <option value="">Any layout</option>
          {LAYOUTS.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>

        <label htmlFor="search-facilities">Required facilities (comma-separated)</label>
        <input id="search-facilities" type="text" value={filters.facilities}
          onChange={change("facilities")} />

        <button type="submit" disabled={searching}>Search</button>
        <button type="button" onClick={clear}>Clear filters</button>
      </form>

      {formError && <p role="alert">{formError}</p>}

      {searchError && (
        <div>
          <p role="alert">{searchError}</p>
          <button type="button" onClick={search}>Retry</button>
        </div>
      )}

      {results && (results.venues.length === 0 ? (
        <p role="status">{results.message}</p>
      ) : (
        <ul aria-label="Matching venues">
          {results.venues.map((venue) => (
            <VenueResult key={venue.id} venue={venue} />
          ))}
        </ul>
      ))}
    </section>
  );
}
