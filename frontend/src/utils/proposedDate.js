// An event's proposed date is Singapore time stored without a time zone: show it as
// recorded, never converted ("2026-12-12T17:00:00" -> "2026-12-12 17:00").
export default function proposedDate(value) {
  return value ? value.slice(0, 16).replace("T", " ") : "Not recorded";
}
