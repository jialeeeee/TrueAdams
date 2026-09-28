// The API sends saved/submitted times as naive UTC ISO strings (possibly with
// microseconds). Show them in the user's local time.
export default function formatSavedAt(iso) {
  return new Date(`${iso.slice(0, 23)}Z`).toLocaleString();
}
