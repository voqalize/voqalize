/** What Fashio is: a demo store, where its products come from (the dataset credit in full), and how the agent works. */
import { Link } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { KAGGLE_URL, MIT_URL } from "../components/Footer";
import { LogoMark } from "../components/Logo";
import { useCatalog } from "../data/catalog";
import { PERSONA } from "../data/persona";
import { POLICY } from "../data/shop";

export function About() {
  const count = useCatalog((s) => s.index?.count);
  const brands = useCatalog((s) => s.index?.brands.length);
  return (
    <div className="wrap about">
      <Breadcrumbs trail={[{ label: "About" }]} />
      <div className="about-head">
        <LogoMark size={56} />
        <h1 className="page-title">About Fashio</h1>
        <p className="about-lede">
          Fashio is a demo fashion store, built to show a voice agent that talks with shoppers and moves the screen for them. You can't buy anything here: no order is shipped and no payment is taken.
        </p>
      </div>
      <div className="about-grid">
        <section>
          <h2>Where the products come from</h2>
          <p>
            Every product, with its name, brand, price, MRP, sizes, description and image, comes from the{" "}
            <a href={KAGGLE_URL} target="_blank" rel="noreferrer">
              Fashion Product Images Dataset
            </a>{" "}
            by Param Aggarwal, published on Kaggle under the{" "}
            <a href={MIT_URL} target="_blank" rel="noreferrer">
              MIT licence
            </a>
            . The dataset was sourced from Myntra. Fashio uses {count ? count.toLocaleString("en-IN") : "several thousand"} of its products{brands ? ` from ${brands} brands` : ""}.
          </p>
          <p>
            Fashio is not Myntra and is not affiliated with Myntra or with any brand shown. Brand names belong to their owners. The Fashio name, logo, colours, policies and pages are the demo's own.
          </p>
          <p>
            Prices and sizes are the dataset's. Stock levels are generated for the demo, so “only 2 left” is made up. Images are served from our own storage bucket, copied from the dataset; a product whose image is still on its way shows a placeholder.
          </p>
        </section>
        <section>
          <h2>How the agent works</h2>
          <p>
            Press the call button in the corner to talk to {PERSONA.name}, in English or Hindi. {PERSONA.name} has one job per page: shopping assistant on the home page and listings, size and fit advisor on a product, gift finder, order tracking, returns, and the in-store kiosk.
          </p>
          <p>
            Everything {PERSONA.name} does on screen is something you could click yourself: setting filters, showing a product, opening the size chart, adding to your bag after you say yes. You always type your own name, phone, address and payment, and you press Place order, Cancel order and Submit return yourself.
          </p>
          <p>Every page also works without the agent.</p>
        </section>
        <section>
          <h2>The store's rules</h2>
          <ul className="about-list">
            <li>{POLICY.delivery.summary}</li>
            <li>{POLICY.returns.summary}</li>
            <li>{POLICY.changes.summary}</li>
            <li>{POLICY.gift_wrap.summary}</li>
          </ul>
          <p>
            <Link to="/shop">Browse the store</Link>
          </p>
        </section>
      </div>
    </div>
  );
}
