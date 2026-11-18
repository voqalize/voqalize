import { MessageSquareText, ShieldCheck } from "lucide-react";
import { CLINIC, DATA, showPhone } from "../data/clinic";
import { actions, useStore } from "../state/store";

export const DEMO_HINT = "Demo patients: 98450 31726 · 99000 48213 · 98860 55102";

/**
 * Phone + one-time code. A demo: no SMS goes out, so the code shows in a
 * "demo SMS" bubble. An unknown number asks for a name and registers a new
 * patient.
 */
export function SignIn({ title = "Sign in with your mobile", note }: { title?: string; note?: string }) {
  const s = useStore((st) => st.signin);
  return (
    <section className="panel signin" data-stage-thing="signin" data-stage-label="Sign in" aria-labelledby="signin-title">
      <div className="panel-head">
        <ShieldCheck size={18} aria-hidden />
        <h3 id="signin-title">{title}</h3>
      </div>
      {note ? <p className="muted small">{note}</p> : null}
      {s.step === "phone" ? (
        <form
          className="signin-form"
          onSubmit={(e) => {
            e.preventDefault();
            actions.sendCode();
          }}
        >
          <label className="field">
            <span>Mobile number</span>
            <span className="phone-input">
              <span className="phone-cc">+91</span>
              <input
                name="phone"
                inputMode="numeric"
                autoComplete="tel-national"
                placeholder="98450 31726"
                value={s.phone}
                onChange={(e) => actions.setPhone(e.target.value)}
              />
            </span>
          </label>
          <button type="submit" className="btn btn-primary">
            Send code
          </button>
        </form>
      ) : null}
      {s.step === "code" ? (
        <>
          <div className="sms" role="status" aria-label="Demo SMS">
            <MessageSquareText size={16} aria-hidden />
            <div>
              <p className="sms-from">Demo SMS to +91 {showPhone(s.phone)}</p>
              <p>
                {DATA.otp.demo_code} is your {CLINIC.short} sign-in code. It expires in 10 minutes.
              </p>
            </div>
          </div>
          <form
            className="signin-form"
            onSubmit={(e) => {
              e.preventDefault();
              actions.verify(s.code);
            }}
          >
            <label className="field">
              <span>4-digit code</span>
              <input
                name="code"
                className="code-input"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={4}
                placeholder="••••"
                value={s.code}
                onChange={(e) => actions.setCode(e.target.value)}
              />
            </label>
            <button type="submit" className="btn btn-primary">
              Verify
            </button>
          </form>
          <button type="button" className="link-btn small" onClick={() => actions.resetSignin()}>
            Use a different number
          </button>
        </>
      ) : null}
      {s.step === "name" ? (
        <form
          className="signin-form"
          onSubmit={(e) => {
            e.preventDefault();
            actions.register(s.name);
          }}
        >
          <p className="small">
            +91 {showPhone(s.phone)} is verified and new to us. What name should we book under?
          </p>
          <label className="field">
            <span>Full name</span>
            <input name="name" autoComplete="name" placeholder="As on your ID" value={s.name} onChange={(e) => actions.setName(e.target.value)} />
          </label>
          <button type="submit" className="btn btn-primary" disabled={!s.name.trim()}>
            Register
          </button>
        </form>
      ) : null}
      {s.error ? (
        <p className="form-error" role="alert">
          {s.error}
        </p>
      ) : null}
      <p className="hint">{DEMO_HINT}</p>
    </section>
  );
}
