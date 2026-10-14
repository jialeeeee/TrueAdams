// The main navigation. Add a new page's link to the group it belongs to.
// A group's `match` decides when its tab is highlighted; the links of the
// highlighted group are shown in the second row.
export const NAV_GROUPS = [
  {
    label: "Events",
    match: (path) => path === "/" || path.startsWith("/events"),
    links: [
      { to: "/", label: "All events", end: true },
      { to: "/events/mine", label: "My event requests" },
      { to: "/events/drafts", label: "My drafts" },
      { to: "/events/requests", label: "My requests" },
      { to: "/events/managed", label: "My managed events" },
      { to: "/events/review-requests", label: "Requests for review" },
    ],
  },
  {
    label: "Venues",
    match: (path) => path.startsWith("/venues"),
    links: [
      { to: "/venues", label: "Venues", end: true },
      { to: "/venues/availability", label: "Venue availability" },
      { to: "/venues/search", label: "Venue search" },
    ],
  },
  {
    label: "Resources",
    match: (path) => path.startsWith("/resources"),
    links: [{ to: "/resources", label: "Resources" }],
  },
  {
    label: "Registrations",
    match: (path) => path.startsWith("/registrations") || path.startsWith("/my-registrations"),
    links: [{ to: "/my-registrations", label: "My registrations" }],
  },
];
