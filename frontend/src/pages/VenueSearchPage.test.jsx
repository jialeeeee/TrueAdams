import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import VenueSearchPage from "./VenueSearchPage.jsx";

// Frontend parts of the cases in docs/test-cases/SCRUM-37-venue-search.md.
// The API itself is covered by backend/tests/test_scrum37_venue_search.py;
// these check what the coordinator sees. Responses mirror that API's contract.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const MATCHED = {
  facilities: ["Projector", "Wi-Fi"],
  accessibility_features: ["Wheelchair ramp"],
  room_layouts: ["theatre"],
};
const AURORA = {
  id: 1, name: "Aurora Ballroom", location: "Level 3, Marina Tower, 10 Bayfront Ave", capacity: 400,
  matches: MATCHED, details_url: "/api/venues/1",
};
const HARBOUR = {
  id: 6, name: "Harbour Room", location: "Level 2, Marina Tower, 10 Bayfront Ave", capacity: 120,
  matches: MATCHED, details_url: "/api/venues/6",
};
const EVERGREEN = {
  id: 5, name: "Evergreen Loft", location: null, capacity: 50,
  matches: { room_layouts: ["u_shape"] }, details_url: "/api/venues/5",
};
const NO_MATCHES = {
  data: { venues: [], message: "No venues match your filters. Try changing or removing some." },
};

const found = (...venues) => ({ data: { venues, message: null } });

function httpFailure(status, error) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true,
    response: { status, data: { error, ...(status === 503 ? { retryable: true } : {}) } },
  });
}

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <VenueSearchPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const field = (label) => screen.getByLabelText(label);
const searchButton = () => screen.getByRole("button", { name: "Search" });

// The query string of the n-th search request (0-based).
function sentQuery(n = 0) {
  const searches = apiClient.get.mock.calls.filter(([url]) => url === "/venues/search");
  return searches[n][1].params.toString();
}

async function fillEveryFilter(user) {
  await user.type(field("Date"), "2026-10-15");
  await user.type(field("Start time"), "18:00");
  await user.type(field("End time"), "21:00");
  await user.type(field("Minimum capacity"), "100");
  await user.type(field("Location"), "Marina Tower");
  await user.type(field("Accessibility needs (comma-separated)"), "Wheelchair ramp");
  await user.selectOptions(field("Layout"), "theatre");
  await user.type(field("Required facilities (comma-separated)"), "Projector, Wi-Fi");
}

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset();
});

describe("VenueSearchPage", () => {
  // TC-37-01 · AC1, AC2, AC5 — every filter is sent, and the results are shown.
  it("sends every filter and lists the matching venues", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(found(AURORA, HARBOUR));
    const user = renderPage();

    await fillEveryFilter(user);
    await user.click(searchButton());

    expect(sentQuery()).toBe(
      "date=2026-10-15&start=18%3A00&end=21%3A00&min_capacity=100&location=Marina+Tower"
      + "&accessibility=Wheelchair+ramp&layout=theatre&facility=Projector&facility=Wi-Fi",
    );
    const results = within(await screen.findByRole("list", { name: "Matching venues" }));
    expect(results.getAllByRole("heading").map((h) => h.textContent))
      .toEqual(["Aurora Ballroom", "Harbour Room"]);
  });

  // TC-37-02 · AC2 — a search with no filters sends no filters.
  it("searches with no filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(found(AURORA));
    const user = renderPage();

    await user.click(searchButton());

    expect(sentQuery()).toBe("");
  });

  // TC-37-05, TC-37-07 · AC1, AC3 — several needs or facilities are sent as separate values.
  it("sends each listed accessibility need and facility separately", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(found(AURORA));
    const user = renderPage();

    await user.type(field("Accessibility needs (comma-separated)"), "Wheelchair ramp, Hearing loop");
    await user.type(field("Required facilities (comma-separated)"), "Stage, PA system , ,Wi-Fi");
    await user.click(searchButton());

    expect(sentQuery()).toBe(
      "accessibility=Wheelchair+ramp&accessibility=Hearing+loop"
      + "&facility=Stage&facility=PA+system&facility=Wi-Fi",
    );
  });

  // TC-37-10 · AC1 — a refusal for this role is shown as a message.
  it("shows the message when the user may not search", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(
      httpFailure(403, "You are not allowed to search venues."),
    );
    const user = renderPage();

    await user.click(searchButton());

    expect((await screen.findByRole("alert")).textContent).toBe("You are not allowed to search venues.");
    expect(screen.queryByRole("list", { name: "Matching venues" })).toBeNull();
  });

  // TC-37-12 to TC-37-15, TC-37-17 · AC1 — invalid filters show the server's message.
  it("shows the server's validation message for invalid filters", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(
      httpFailure(400, "Enter the date, start time and end time together."),
    );
    const user = renderPage();

    await user.type(field("Date"), "2026-10-15");
    await user.click(searchButton());

    expect((await screen.findByRole("alert")).textContent)
      .toBe("Enter the date, start time and end time together.");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });

  // TC-37-28 · AC5 — a result shows identity, location, capacity and what matched.
  it("shows each result's location, capacity and matching characteristics", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(found(AURORA));
    const user = renderPage();

    await user.click(searchButton());

    const aurora = within(await screen.findByRole("listitem", { name: "Aurora Ballroom" }));
    expect(aurora.getByText("Location: Level 3, Marina Tower, 10 Bayfront Ave")).toBeTruthy();
    expect(aurora.getByText("Capacity: 400")).toBeTruthy();
    expect(aurora.getByText("Matches: Projector, Wi-Fi, Wheelchair ramp, theatre")).toBeTruthy();
  });

  // TC-37-28 · AC5 — "View details" opens that venue's details (SCRUM-35 endpoint).
  it("shows a venue's details on request", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce(found(AURORA))
      .mockResolvedValueOnce({
        data: {
          id: 1, name: "Aurora Ballroom", description: "Pillarless ballroom.",
          facilities: ["Stage", "Projector"], accessibility_features: ["Hearing loop"],
          room_layouts: ["theatre"], operating_hours: "Mon-Sun 08:00-23:00",
        },
      });
    const user = renderPage();
    await user.click(searchButton());

    await user.click(await screen.findByRole("button", { name: "View details" }));

    expect(apiClient.get).toHaveBeenLastCalledWith("/venues/1");
    const details = within(await screen.findByLabelText("Aurora Ballroom details"));
    expect(details.getByText("Pillarless ballroom.")).toBeTruthy();
    expect(details.getByText("Mon-Sun 08:00-23:00")).toBeTruthy();
  });

  // TC-37-29 · AC5 — a location that was never recorded says so.
  it("shows 'Not recorded' for a missing location", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(found(EVERGREEN));
    const user = renderPage();

    await user.selectOptions(field("Layout"), "u_shape");
    await user.click(searchButton());

    const evergreen = within(await screen.findByRole("listitem", { name: "Evergreen Loft" }));
    expect(evergreen.getByText("Location: Not recorded")).toBeTruthy();
  });

  // TC-37-30 · AC6 — no matches: a message, filters kept, and revising works.
  it("keeps the filters after no matches so they can be revised", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(NO_MATCHES).mockResolvedValueOnce(found(AURORA));
    const user = renderPage();
    await user.type(field("Minimum capacity"), "1000");
    await user.click(searchButton());

    expect((await screen.findByRole("status")).textContent)
      .toBe("No venues match your filters. Try changing or removing some.");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(field("Minimum capacity").value).toBe("1000");

    await user.clear(field("Minimum capacity"));
    await user.type(field("Minimum capacity"), "300");
    await user.click(searchButton());

    expect(sentQuery(1)).toBe("min_capacity=300");
    expect(await screen.findByRole("listitem", { name: "Aurora Ballroom" })).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });

  // TC-37-31 · AC6 — an unknown facility gives the no-matches message, not an error.
  it("shows no matches, not an error, for an unknown facility", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(NO_MATCHES);
    const user = renderPage();

    await user.type(field("Required facilities (comma-separated)"), "Helipad");
    await user.click(searchButton());

    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  // TC-37-32, TC-37-33 · AC7 — a failed search is an error, never "no matches".
  it("shows an error with Retry, not 'no matches', when the search fails", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(
      httpFailure(503, "The venue search could not be completed. Please try again."),
    );
    const user = renderPage();

    await user.click(searchButton());

    expect((await screen.findByRole("alert")).textContent).toContain("could not be completed");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByText(/No venues match/)).toBeNull();
    expect(screen.queryByRole("list", { name: "Matching venues" })).toBeNull();
  });

  // TC-37-34 · AC7 — Retry repeats the same search once the service is back.
  it("retries with the same filters", async () => {
    vi.mocked(apiClient.get)
      .mockRejectedValueOnce(httpFailure(503, "The venue search could not be completed. Please try again."))
      .mockResolvedValueOnce(found(AURORA, HARBOUR));
    const user = renderPage();
    await user.type(field("Minimum capacity"), "100");
    await user.click(searchButton());

    await user.click(await screen.findByRole("button", { name: "Retry" }));

    expect(sentQuery(1)).toBe("min_capacity=100");
    expect(field("Minimum capacity").value).toBe("100");
    expect(await screen.findByRole("listitem", { name: "Harbour Room" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
