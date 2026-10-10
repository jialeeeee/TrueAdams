// Who decided a request, shown with its outcome (SCRUM-60). A decision saved before
// the decider was recorded says so plainly rather than hiding the line.
export default function decidedBy(request) {
  const email = request.decided_by?.email;
  return email ? `Decided by ${email}` : "Decided by: not recorded";
}
