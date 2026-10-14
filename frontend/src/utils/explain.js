// The message to show for a failed request: the server's own `error` text when it
// sent one, otherwise the page's fallback (for example when the network is down).
export default function explain(failure, fallback) {
  const error = failure.response?.data?.error;
  return typeof error === "string" && error.trim() ? error : fallback;
}
