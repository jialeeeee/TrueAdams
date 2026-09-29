// Event request statuses as shown to users.
const LABELS = {
  draft: "Draft",
  submitted: "Submitted",
  under_review: "Under review",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
};

export default function statusLabel(status) {
  return LABELS[status] ?? status.charAt(0).toUpperCase() + status.slice(1);
}
