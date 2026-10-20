// What Technical Support Staff can say about an equipment requirement (SCRUM-42 A7), in
// display order. None says reserved or fulfilled: reserving is SCRUM-44.
// Must match ARRANGEMENT_STATUSES in backend/app/events/equipment.py.
const ARRANGEMENT_STATUSES = [
  ["requested", "Requested"],
  ["being_arranged", "Being arranged"],
  ["unavailable", "Suitable equipment unavailable"],
];

export default ARRANGEMENT_STATUSES;
