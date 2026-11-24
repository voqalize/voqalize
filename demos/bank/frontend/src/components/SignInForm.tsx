import { useId, useState } from "react";
import { type SignInProblem, noteHand, useSession } from "../state/session";

const WHY: Record<SignInProblem, string> = {
  mobile: "Enter your 10-digit mobile number (it starts with 6, 7, 8 or 9).",
  pin: "Enter your 4-digit PIN.",
};

/**
 * The sign-in form (FEEDBACK B7, X9): a 10-digit mobile number and a 4-digit PIN,
 * both typed by the customer, nothing pre-filled. Only the customer's own click,
 * tap or Enter on Sign in signs in (`noteHand`, `useSession.signIn`). What is
 * typed stays in this component: it is never sent to the brain, never marked for
 * Stage and never put in a store.
 */
export function SignInForm({ onSignedIn, compact = false }: { onSignedIn: () => void; compact?: boolean }) {
  const signIn = useSession((s) => s.signIn);
  const id = useId();
  const [mobile, setMobile] = useState("");
  const [pin, setPin] = useState("");
  const [problem, setProblem] = useState<SignInProblem | null>(null);

  return (
    <form
      className={compact ? "signin-form signin-form--compact" : "signin-form"}
      data-stage-thing="sign-in-form"
      data-stage-label="Sign in"
      aria-label="Sign in to My banking"
      noValidate
      onPointerDownCapture={(e) => noteHand(e.nativeEvent)}
      onKeyDownCapture={(e) => noteHand(e.nativeEvent)}
      onSubmit={(e) => {
        e.preventDefault();
        const out = signIn(mobile, pin);
        if (out.ok) {
          setProblem(null);
          onSignedIn();
        } else if (out.problem !== "hand") {
          setProblem(out.problem);
        }
      }}
    >
      <div className="field">
        <label className="field-label" htmlFor={`${id}-mobile`}>
          Mobile number
        </label>
        <div className="input-wrap signin-mobile">
          <span className="signin-prefix" aria-hidden>
            +91
          </span>
          <input
            id={`${id}-mobile`}
            name="mobile"
            className="input"
            type="tel"
            inputMode="numeric"
            autoComplete="tel-national"
            placeholder="10-digit mobile number"
            maxLength={10}
            value={mobile}
            aria-invalid={problem === "mobile"}
            aria-describedby={problem === "mobile" ? `${id}-err` : undefined}
            onChange={(e) => {
              setMobile(e.target.value.replace(/\D/g, "").slice(0, 10));
              if (problem === "mobile") setProblem(null);
            }}
          />
        </div>
      </div>
      <div className="field">
        <label className="field-label" htmlFor={`${id}-pin`}>
          4-digit PIN
        </label>
        <input
          id={`${id}-pin`}
          name="pin"
          className="input pin-input"
          type="password"
          inputMode="numeric"
          autoComplete="current-password"
          placeholder="••••"
          maxLength={4}
          value={pin}
          aria-invalid={problem === "pin"}
          aria-describedby={problem === "pin" ? `${id}-err` : undefined}
          onChange={(e) => {
            setPin(e.target.value.replace(/\D/g, "").slice(0, 4));
            if (problem === "pin") setProblem(null);
          }}
        />
      </div>
      {problem ? (
        <p id={`${id}-err`} className="field-error" role="alert">
          {WHY[problem]}
        </p>
      ) : null}
      <button
        type="submit"
        className={`btn btn-primary btn-block${compact ? "" : " btn-lg"}`}
        data-stage-thing="login:submit"
        data-stage-label="Sign in"
      >
        Sign in
      </button>
    </form>
  );
}
