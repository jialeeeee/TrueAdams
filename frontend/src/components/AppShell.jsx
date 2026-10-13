import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { isSignedIn, signOut } from "../utils/session.js";
import { NAV_GROUPS } from "./navigation.js";

// The page chrome: top bar, grouped navigation, sign-in state and the content
// column. Pages render as children and need no layout of their own.
export default function AppShell({ children }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  // Read on every render. Logging in or out changes the location, which re-renders this.
  const signedIn = isSignedIn();
  const group = NAV_GROUPS.find((candidate) => candidate.match(pathname));

  const handleLogout = () => {
    signOut();
    navigate("/login");
  };

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="app-header">
        <div className="app-bar">
          <Link className="app-brand" to="/">ConnectSphere</Link>
          <nav className="app-nav" aria-label="Main">
            <ul>
              {NAV_GROUPS.map((item) => (
                <li key={item.label}>
                  <Link
                    to={item.links[0].to}
                    className={item === group ? "is-active" : undefined}
                    aria-current={item === group ? "true" : undefined}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="app-session">
            {signedIn ? (
              <button type="button" onClick={handleLogout}>Log out</button>
            ) : (
              <NavLink to="/login">Login</NavLink>
            )}
          </div>
        </div>
        {group && group.links.length > 1 && (
          <nav className="app-subnav" aria-label={`${group.label} pages`}>
            <div className="app-subnav-inner">
              <ul>
                {group.links.map((link) => (
                  <li key={link.to}>
                    <NavLink to={link.to} end={link.end}>{link.label}</NavLink>
                  </li>
                ))}
              </ul>
            </div>
          </nav>
        )}
      </header>
      <main className="app-main" id="main">
        {children}
      </main>
    </>
  );
}
