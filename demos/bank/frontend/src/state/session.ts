/**
 * Sign-in (FEEDBACK B7, X9). No real authentication: any valid 10-digit mobile
 * number and any 4-digit PIN open the sample customer's banking. But the customer
 * types both and presses Sign in with their own hand; nothing is pre-filled, the
 * agent has no move that types or submits here, and a submit the page did not see
 * a hand make (a script's `click()` or `requestSubmit()`, an agent's move) is
 * refused. The brain is told who signed in, never the number or the PIN.
 * Kept in sessionStorage so a refresh stays signed in.
 */
import { create } from "zustand";
import { customer } from "../data/bank";
import { currentBy, emit } from "../voice/events";

const KEY = "globalbank-signed-in";
const stored = () => {
  try {
    return sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
};

/** What is wrong with what was typed, by field; null when it is the right shape. */
export type SignInProblem = "mobile" | "pin";

/** A mobile number is 10 digits starting 6 to 9; the PIN is 4 digits. */
export const MOBILE_RE = /^[6-9]\d{9}$/;
export const PIN_RE = /^\d{4}$/;

export function checkSignIn(mobile: string, pin: string): SignInProblem | null {
  if (!MOBILE_RE.test(mobile)) return "mobile";
  if (!PIN_RE.test(pin)) return "pin";
  return null;
}

/**
 * Only the customer's own hand signs in. The sign-in form notes every trusted
 * pointer or key press on it (`noteHand`); a script's `click()`, `dispatchEvent`
 * or `requestSubmit()` makes none. A submit with no such press just before it,
 * or one made while the agent is acting, is refused.
 */
let handAt = Number.NEGATIVE_INFINITY;
export const noteHand = (e: { isTrusted: boolean }) => {
  if (e.isTrusted) handAt = Date.now();
};
export const pressedByHand = (): boolean => Date.now() - handAt < 1500 && currentBy() !== "agent";

/** What a sign-in attempt came to. */
export type SignInOutcome = { ok: true } | { ok: false; problem: SignInProblem | "hand" };

interface Session {
  signedIn: boolean;
  /** The customer's own press on Sign in, with what they typed. */
  signIn: (mobile: string, pin: string) => SignInOutcome;
  signOut: () => void;
}

export const useSession = create<Session>((set) => ({
  signedIn: stored(),
  signIn: (mobile, pin) => {
    if (!pressedByHand()) {
      console.warn("[bank] sign-in refused: only the customer's own press on Sign in signs in");
      return { ok: false, problem: "hand" };
    }
    const problem = checkSignIn(mobile.replace(/\D/g, ""), pin);
    if (problem) {
      emit("sign_in_failed", { problem }, "visitor");
      return { ok: false, problem };
    }
    try {
      sessionStorage.setItem(KEY, "1");
    } catch {
      /* private mode */
    }
    set({ signedIn: true });
    emit("signed_in", { name: customer.profile.name, first_name: customer.profile.first_name }, "visitor");
    return { ok: true };
  },
  signOut: () => {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* private mode */
    }
    set({ signedIn: false });
    emit("signed_out", {});
  },
}));
