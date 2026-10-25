// An event's registration numbers for its organiser (SCRUM-54 AC1): one line each for
// places taken, capacity and places left. Without a capacity, registration has not been
// set up, so there are no places to count against.
const NOT_SET_UP = "Not set up";

export default function registrationSummary(registration) {
  return [
    `Registrations: ${registration.registered_count}`,
    `Capacity: ${registration.capacity ?? NOT_SET_UP}`,
    `Remaining places: ${registration.slots_remaining ?? NOT_SET_UP}`,
  ];
}
