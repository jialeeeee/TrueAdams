// Whether a failed request can simply be tried again: a network failure (no response),
// or one the server marks `retryable`. A refusal such as a 403 cannot.
export default function canRetry(failure) {
  return !failure.response || failure.response.data?.retryable === true;
}
