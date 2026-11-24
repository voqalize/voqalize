import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { brand, customer } from "../../data/bank";
import { persona } from "../../persona";
import { useSession } from "../../state/session";

/**
 * The mock sign-in. On /login it lands on /app (or `?from=`); rendered in
 * place of a signed-in screen by the shell's guard, signing in simply lets
 * that screen render (`from` is where the visitor already is).
 */
export function Login({ from }: { from?: string }) {
  const signIn = useSession((s) => s.signIn);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [pin, setPin] = useState("123456");
  const guarded = from != null;

  return (
    <main className="page login-page" data-stage-thing="screen:login" data-stage-label="Sign in">
      <div className="wrap login-grid">
        <section className="login-card" aria-labelledby="login-h">
          <h1 id="login-h" className="login-title">
            Sign in to My banking
          </h1>
          {guarded ? <p className="login-why">That page is in My banking. Sign in to see it.</p> : null}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              signIn();
              if (!guarded) navigate(params.get("from") || "/app");
            }}
          >
            <div className="field">
              <label className="field-label" htmlFor="login-cid">
                Customer ID
              </label>
              <input id="login-cid" name="customer_id" className="input" defaultValue={customer.profile.customer_id} autoComplete="username" />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="login-pin">
                6-digit PIN
              </label>
              <input
                id="login-pin"
                name="pin"
                className="input pin-input"
                type="password"
                inputMode="numeric"
                maxLength={6}
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
                autoComplete="current-password"
              />
            </div>
            <button type="submit" className="btn btn-primary btn-block btn-lg" data-stage-thing="login:submit" data-stage-label="Sign in">
              Sign in
            </button>
          </form>
          <p className="login-demo">
            <ShieldCheck size={15} aria-hidden /> This is a demo with no real sign-in. Any PIN works, and you see a sample customer's accounts.
          </p>
        </section>
        <aside className="login-side">
          <h2>Inside My banking</h2>
          <ul>
            <li>Savings and current accounts, with every transaction searchable</li>
            <li>Debit and credit card controls: block, limits, international use</li>
            <li>Bills, transfers to saved payees, fixed deposits</li>
            <li>Spending by category, month by month</li>
          </ul>
          <p>
            Ask {persona.name} instead of looking: “When is my card bill due?” opens the statement and points at the date.
          </p>
          <p className="login-new">
            New to {brand.short}? <Link to="/open-account">Open a savings account</Link>
          </p>
        </aside>
      </div>
    </main>
  );
}
