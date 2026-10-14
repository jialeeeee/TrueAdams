// Event and registration times are Singapore time stored without a time zone.
// Show them as recorded, never converted: "2026-11-20T10:00:00" -> "20/11/2026 10:00 SGT".
export default function singaporeTime(value) {
  const [date, time] = value.slice(0, 16).split("T");
  const [year, month, day] = date.split("-");
  return `${day}/${month}/${year} ${time} SGT`;
}
