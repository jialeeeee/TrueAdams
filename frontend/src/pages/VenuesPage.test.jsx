import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import VenuesPage from "./VenuesPage.jsx";

// SCRUM-35 "View Venue Details": frontend cases TC-35-13 to TC-35-17 in
// docs/test-cases/SCRUM-35-view-venue-details.md. Responses mirror
// backend/tests/test_venue_details.py:
//   GET /venues/      -> { venues: [{ id, name, location, capacity, is_available }], message }
//                        message is the empty-state text, null when venues are listed
//   GET /venues/<id>  -> every planning field, null when never recorded, and not_recorded
//   failures          -> { error, retryable: true } (503), or a refusal such as 403

vi.mock("../api/client.js", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

const AURORA = {
  id: 1, name: "Aurora Ballroom", location: "Level 3, Marina Tower, 10 Bayfront Ave",
  capacity: 400, is_available: true,
};
const BAYFRONT = { id: 2, name: "Bayfront Pavilion", location: "Bayfront Park, East Lawn",
  capacity: null, is_available: true };
const CIVIC_DETAILS = {
  id: 3, name: "Civic Hall", is_available: true,
  description: "Community hall available for bare-venue hire.", location: "12 Civic Road",
  capacity: 80, area_sqm: 150, facilities: [], accessibility_features: [],
  room_layouts: ["theatre"], operating_hours: "Mon-Fri 09:00-18:00",
  contact_email: "hire@civichall.test", contact_phone: "+65 6000 1111", parking_spaces: 0,
  catering_available: false, setup_minutes: 0, turnaround_minutes: 0, not_recorded: [],
};
const BAYFRONT_DETAILS = {
  id: 2, name: "Bayfront Pavilion", is_available: true, description: null,
  location: "Bayfront Park, East Lawn", capacity: null, area_sqm: null,
  facilities: ["Covered stage"], accessibility_features: null, room_layouts: null,
  operating_hours: null, contact_email: null, contact_phone: null, parking_spaces: null,
  catering_available: null, setup_minutes: null, turnaround_minutes: null,
  not_recorded: ["description", "capacity", "area_sqm", "accessibility_features", "room_layouts",
    "operating_hours", "contact_email", "contact_phone", "parking_spaces", "catering_available",
    "setup_minutes", "turnaround_minutes"],
};
const EMPTY = "No venues have been recorded yet.";
const OUTAGE = "Venues could not be loaded. Please try again.";

function failure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

// Venue Staff are refused nothing here; the options call only decides Add and Edit.
function serve(routes) {
  apiClient.get.mockImplementation(async (url) => {
    if (url === "/venues/options") throw failure(403, { error: "Only Venue Staff can add or edit venues." });
    const answer = routes[url];
    if (answer === undefined) throw new Error(`unexpected GET ${url}`);
    if (answer instanceof Error) throw answer;
    return { data: typeof answer === "function" ? answer() : answer };
  });
}

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <VenuesPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const item = async (name) => within(await screen.findByRole("listitem", { name }));

beforeEach(() => {
  Object.values(apiClient).forEach((fn) => fn.mockReset());
});

describe("SCRUM-35 browsing venues", () => {
  // TC-35-13 · AC1, AC3
  it("lists each venue with its location and capacity, saying when one isn't recorded", async () => {
    serve({ "/venues/": { venues: [AURORA, BAYFRONT], message: null } });
    renderPage();

    const aurora = await item("Aurora Ballroom");
    expect(aurora.getByText("Location: Level 3, Marina Tower, 10 Bayfront Ave")).toBeTruthy();
    expect(aurora.getByText("Capacity: 400")).toBeTruthy();
    const bayfront = await item("Bayfront Pavilion");
    expect(bayfront.getByText("Capacity: Not recorded")).toBeTruthy();
    expect(screen.queryByText(EMPTY)).toBeNull();
  });

  // TC-35-14 · AC4
  it("shows the server's empty-state message when no venues are recorded", async () => {
    serve({ "/venues/": { venues: [], message: EMPTY } });
    renderPage();

    expect(await screen.findByText(EMPTY)).toBeTruthy();
    expect(screen.queryByRole("listitem")).toBeNull();
  });

  // TC-35-15 · AC5
  it("says the list could not be loaded, never that there are no venues, and retries", async () => {
    let fail = true;
    serve({ "/venues/": () => {
      if (fail) throw failure(503, { error: OUTAGE, retryable: true });
      return { venues: [AURORA], message: null };
    } });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toBe(OUTAGE);
    expect(screen.queryByText(EMPTY)).toBeNull();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await item("Aurora Ballroom")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  // TC-35-15 · AC5
  it("explains a network failure with its own words, and a refusal without offering a retry", async () => {
    serve({ "/venues/": new Error("Network Error") });
    const { unmount } = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><VenuesPage /></MemoryRouter>,
    );
    expect((await screen.findByRole("alert")).textContent)
      .toBe("Venues could not be loaded. Check your connection and try again.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    unmount();

    serve({ "/venues/": failure(403, { error: "Only event coordinators and Venue Staff can view venues." }) });
    renderPage();
    expect((await screen.findByRole("alert")).textContent)
      .toBe("Only event coordinators and Venue Staff can view venues.");
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });
});

describe("SCRUM-35 a venue's details", () => {
  // TC-35-16 · AC2, AC3
  it("shows every planning characteristic, and recorded absences as None, No or 0", async () => {
    serve({ "/venues/": { venues: [{ id: 3, name: "Civic Hall", location: "12 Civic Road", capacity: 80, is_available: true }], message: null },
      "/venues/3": CIVIC_DETAILS });
    const user = renderPage();

    await user.click((await item("Civic Hall")).getByRole("button", { name: "View details" }));

    expect(apiClient.get).toHaveBeenLastCalledWith("/venues/3");
    const details = within(await screen.findByLabelText("Civic Hall details"));
    const value = (term) => details.getByText(term).nextElementSibling.textContent;
    expect(value("Description")).toBe("Community hall available for bare-venue hire.");
    expect(value("Area (m²)")).toBe("150");
    expect(value("Facilities")).toBe("None");
    expect(value("Accessibility")).toBe("None");
    expect(value("Layouts")).toBe("theatre");
    expect(value("Operating hours")).toBe("Mon-Fri 09:00-18:00");
    expect(value("Contact")).toBe("hire@civichall.test, +65 6000 1111");
    expect(value("Parking spaces")).toBe("0");
    expect(value("Catering")).toBe("No");
    expect(value("Setup time")).toBe("0 min");
    expect(value("Turnaround time")).toBe("0 min");
    expect(details.queryByText("Not recorded")).toBeNull();
  });

  // TC-35-16 · AC3
  it("marks every field the server says wasn't recorded as Not recorded, never as None", async () => {
    serve({ "/venues/": { venues: [BAYFRONT], message: null }, "/venues/2": BAYFRONT_DETAILS });
    const user = renderPage();

    await user.click((await item("Bayfront Pavilion")).getByRole("button", { name: "View details" }));

    const details = within(await screen.findByLabelText("Bayfront Pavilion details"));
    const value = (term) => details.getByText(term).nextElementSibling.textContent;
    expect(value("Facilities")).toBe("Covered stage");
    for (const term of ["Description", "Capacity", "Area (m²)", "Accessibility", "Layouts",
      "Operating hours", "Contact", "Parking spaces", "Catering", "Setup time", "Turnaround time"]) {
      expect(value(term)).toBe("Not recorded");
    }
    expect(details.queryByText("None")).toBeNull();
  });

  // TC-35-17 · AC5
  it("explains details that could not be loaded and loads them on another try", async () => {
    let fail = true;
    serve({ "/venues/": { venues: [AURORA], message: null }, "/venues/1": () => {
      if (fail) throw failure(503, { error: " ", retryable: true });
      return { ...CIVIC_DETAILS, id: 1, name: "Aurora Ballroom", catering_available: true };
    } });
    const user = renderPage();
    const aurora = await item("Aurora Ballroom");

    await user.click(aurora.getByRole("button", { name: "View details" }));
    expect((await aurora.findByRole("alert")).textContent)
      .toBe("Venue details could not be loaded. Please try again.");
    expect(screen.queryByLabelText("Aurora Ballroom details")).toBeNull();

    fail = false;
    await user.click(aurora.getByRole("button", { name: "View details" }));
    const details = within(await screen.findByLabelText("Aurora Ballroom details"));
    expect(details.getByText("Catering").nextElementSibling.textContent).toBe("Yes");
    expect(aurora.queryByRole("alert")).toBeNull();
  });
});
