import { useState } from "react";
import { Link } from "react-router-dom";
import { ROOMS } from "../data/catalog";
import { INFO_PAGES, site } from "../data/content";
import { Wordmark } from "./Header";

export function Footer() {
  const [joined, setJoined] = useState(false);
  return (
    <footer className="site-footer">
      <div className="wrap footer-top">
        <div className="footer-letter">
          <h2 className="h3">Letters from the studio</h2>
          <p className="small">{site.newsletter}</p>
          {joined ? (
            <p className="footer-thanks" role="status">
              Thank you. This is a demo store, so nothing will arrive, but that is how it would feel.
            </p>
          ) : (
            <form
              className="footer-form"
              onSubmit={(e) => {
                e.preventDefault();
                setJoined(true);
              }}
            >
              <label className="sr-only" htmlFor="footer-email">
                Email address
              </label>
              <input id="footer-email" className="input" type="email" required placeholder="Email address" autoComplete="email" />
              <button type="submit" className="btn btn-primary">
                Sign up
              </button>
            </form>
          )}
        </div>
        <div className="footer-cols">
          <div>
            <h3 className="footer-h">Shop</h3>
            <ul>
              {ROOMS.map((r) => (
                <li key={r.id}>
                  <Link to={`/room/${r.id}`}>{r.name}</Link>
                </li>
              ))}
              <li>
                <Link to="/sale">Sale</Link>
              </li>
            </ul>
          </div>
          <div>
            <h3 className="footer-h">Help</h3>
            <ul>
              <li>
                <Link to="/returns">Start a return</Link>
              </li>
              {INFO_PAGES.filter((p) => p.slug !== "about").map((p) => (
                <li key={p.slug}>
                  <Link to={p.path}>{p.label}</Link>
                </li>
              ))}
              <li>
                <Link to="/contact">Contact</Link>
              </li>
            </ul>
          </div>
          <div>
            <h3 className="footer-h">Fernhollow</h3>
            <ul>
              <li>
                <Link to="/about">About</Link>
              </li>
              <li>
                <Link to="/journal">Journal</Link>
              </li>
              <li>
                <Link to="/board">Plan a room</Link>
              </li>
              <li>
                <Link to="/shop">All pieces</Link>
              </li>
            </ul>
          </div>
        </div>
      </div>
      <div className="wrap footer-bottom">
        <Wordmark />
        <p className="small">{site.footerTagline}</p>
        <p className="small footer-fine">
          Fernhollow is a fictional store, built as a voice demo by{" "}
          <a className="link" href="https://voqalize.com">
            Voqalize
          </a>
          . No orders are fulfilled and no payment is taken.
        </p>
      </div>
    </footer>
  );
}
