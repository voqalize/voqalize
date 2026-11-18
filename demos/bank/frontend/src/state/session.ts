/** The mock sign-in: no real auth. Kept in sessionStorage so a refresh stays signed in. */
import { create } from "zustand";
import { customer } from "../data/bank";
import { emit } from "../voice/events";

const KEY = "anvaya-signed-in";
const stored = () => {
  try {
    return sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
};

interface Session {
  signedIn: boolean;
  signIn: () => void;
  signOut: () => void;
}

export const useSession = create<Session>((set) => ({
  signedIn: stored(),
  signIn: () => {
    try {
      sessionStorage.setItem(KEY, "1");
    } catch {
      /* private mode */
    }
    set({ signedIn: true });
    emit("signed_in", { customer_id: customer.profile.customer_id });
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
