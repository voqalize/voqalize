import { Link } from "react-router-dom";
import { brand, products } from "../data/bank";
import { Logo } from "./Logo";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="wrap footer-grid">
        <div className="footer-brand">
          <Logo />
          <p className="footer-tag">{brand.tagline}</p>
          <p className="footer-help">
            Helpline <strong>{brand.helpline}</strong>, every day, 8 am to 10 pm.
          </p>
        </div>
        <nav aria-label="Accounts">
          <h2 className="footer-h">Accounts</h2>
          <Link to="/open-account">Open a savings account</Link>
          {products.savings_variants.map((v) => (
            <Link key={v.id} to="/open-account">
              {v.name.replace("Anvaya ", "")}
            </Link>
          ))}
        </nav>
        <nav aria-label="Cards">
          <h2 className="footer-h">Credit cards</h2>
          <Link to="/cards">Find your card</Link>
          <Link to="/cards/compare">Compare cards</Link>
          <Link to="/cards/emi">EMI planner</Link>
          <Link to="/cards/apply">Apply</Link>
        </nav>
        <nav aria-label="Loans">
          <h2 className="footer-h">Loans</h2>
          {products.loans.map((l) => (
            <Link key={l.id} to={`/loans/${l.id}`}>
              {l.short}
            </Link>
          ))}
          <Link to="/loans/apply">Apply for a loan</Link>
        </nav>
        <nav aria-label="My banking">
          <h2 className="footer-h">My banking</h2>
          <Link to="/login">Sign in</Link>
          <Link to="/app/transactions">Transactions</Link>
          <Link to="/app/bills">Pay bills</Link>
          <Link to="/app/deposits">Fixed deposits</Link>
        </nav>
      </div>
      <div className="wrap footer-legal">
        <p className="footer-disclaimer">
          <strong>Fictional bank — sample data.</strong> {brand.disclaimer}
        </p>
        <p className="footer-small">Not a real bank, not regulated, not an offer. No real account, card or loan can be opened here.</p>
      </div>
    </footer>
  );
}
