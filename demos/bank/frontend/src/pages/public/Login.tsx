import { ShieldCheck } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { SignInForm } from "../../components/SignInForm";
import { brand } from "../../data/bank";
import { persona } from "../../persona";

/**
 * The sign-in screen: the customer types a mobile number and PIN and presses
 * Sign in (SignInForm). On /login it lands on /app (or `?from=`); rendered in
 * place of a signed-in screen by the shell's guard, signing in simply lets
 * that screen render (`from` is where the visitor already is).
 */
export function Login({ from }: { from?: string }) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const guarded = from != null;

  return (
    <main className="page login-page" data-stage-thing="screen:login" data-stage-label="Sign in">
      <div className="wrap login-grid">
        <section className="login-card" aria-labelledby="login-h">
          <h1 id="login-h" className="login-title">
            Sign in to My banking
          </h1>
          {guarded ? <p className="login-why">That page is in My banking. Sign in to see it.</p> : null}
          <SignInForm
            onSignedIn={() => {
              if (!guarded) navigate(params.get("from") || "/app");
            }}
          />
          <p className="login-demo">
            <ShieldCheck size={15} aria-hidden /> A demo with no real sign-in: any 10-digit mobile number and any 4-digit PIN open a sample customer's accounts. Type them yourself; the assistant never asks for them.
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
