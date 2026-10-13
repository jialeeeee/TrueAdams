// The signed-in state, kept in sessionStorage["access_token"] (see LoginPage and
// api/client.js). The token only carries the user's id, so nothing here knows the
// user's role; the backend checks the role from the database on every request.
const TOKEN_KEY = "access_token";

export function readToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

// A JWT's expiry in seconds since the epoch, or null when the token is not a
// readable JWT (the server stays the judge of whether it is valid).
function expiry(token) {
  try {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const { exp } = JSON.parse(atob(payload));
    return typeof exp === "number" ? exp : null;
  } catch {
    return null;
  }
}

// True when a token is stored and has not visibly expired. Used for display only,
// to choose between "Login" and "Log out".
export function isSignedIn(token = readToken()) {
  if (typeof token !== "string" || !token.trim()) return false;
  const exp = expiry(token);
  return exp === null || exp * 1000 > Date.now();
}

export function signOut() {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage is unavailable: there is nothing stored to remove.
  }
}
