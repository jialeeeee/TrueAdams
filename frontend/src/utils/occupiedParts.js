// SCRUM-84: a booking or hold occupies its setup before and turnaround after the event.
// The server gives `setup` and `turnaround` ({start, end, minutes}) only when there is one;
// times are Singapore time without a time zone, shown as recorded.
const asText = (value) => value.slice(0, 16).replace("T", " ");

// "setup 09:30 to 10:00, turnaround 12:00 to 12:45", or "" when there is neither.
export default function occupiedParts(item) {
  const clock = (value) => value.slice(11, 16);
  const day = (value) => value.slice(0, 10);
  const range = (part) =>
    (day(part.start) === day(part.end)
      ? `${clock(part.start)} to ${clock(part.end)}`
      : `${asText(part.start)} to ${asText(part.end)}`);
  const parts = [];
  if (item.setup) parts.push(`setup ${range(item.setup)}`);
  if (item.turnaround) parts.push(`turnaround ${range(item.turnaround)}`);
  return parts.join(", ");
}
