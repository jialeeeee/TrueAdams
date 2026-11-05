// SCRUM-35 AC2, AC3: a venue's planning characteristics, from GET /venues/<id>.
// A field the server lists in not_recorded (or leaves out) is "Not recorded"; a recorded
// absence is a fact and says so ("None", "No", "0"), so the two never look alike (CF08).
// Used by the Venues page and by venue search (SCRUM-37).

const NOT_RECORDED = "Not recorded";

function missing(details, field) {
  return details[field] === null || details[field] === undefined
    || (details.not_recorded ?? []).includes(field);
}

function list(details, field) {
  if (missing(details, field)) return NOT_RECORDED;
  return details[field].length ? details[field].join(", ") : "None";
}

function plain(details, field, unit = "") {
  return missing(details, field) ? NOT_RECORDED : `${details[field]}${unit}`;
}

function contact(details) {
  const known = ["contact_email", "contact_phone"].filter((field) => !missing(details, field));
  return known.length ? known.map((field) => details[field]).join(", ") : NOT_RECORDED;
}

// `name` labels the list; venue search passes the result's name.
export default function VenueDetails({ details, name = details.name }) {
  const rows = [
    ["Description", plain(details, "description")],
    ["Location", plain(details, "location")],
    ["Capacity", plain(details, "capacity")],
    ["Area (m²)", plain(details, "area_sqm")],
    ["Facilities", list(details, "facilities")],
    ["Accessibility", list(details, "accessibility_features")],
    ["Layouts", list(details, "room_layouts")],
    ["Operating hours", plain(details, "operating_hours")],
    ["Contact", contact(details)],
    ["Parking spaces", plain(details, "parking_spaces")],
    ["Catering", missing(details, "catering_available") ? NOT_RECORDED
      : (details.catering_available ? "Yes" : "No")],
    ["Setup time", plain(details, "setup_minutes", " min")],
    ["Turnaround time", plain(details, "turnaround_minutes", " min")],
  ];
  return (
    <dl aria-label={`${name} details`}>
      {rows.map(([term, value]) => [<dt key={`${term}-t`}>{term}</dt>, <dd key={`${term}-d`}>{value}</dd>])}
    </dl>
  );
}
