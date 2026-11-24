/**
 * The shell: routes, the Stage host and its performers, the router seam
 * performers navigate through, `page_viewed` on every route change, the voice
 * dock, and (with `?debug=1`) the move console. `/app/*` while signed out
 * renders the sign-in screen in place of the screen asked for.
 */
import { Suspense, lazy, useEffect, useRef } from "react";
import { BrowserRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ConfirmSheet } from "./app/ConfirmSheet";
import * as A from "./pages/app";
import * as P from "./pages/public";
import { useStageHost } from "./stage/host";
import { bindRouter, screenOf } from "./stage/nav";
import { usePerformers } from "./stage/performers";
import { useSession } from "./state/session";
import { useDebugHarness } from "./voice/debugHarness";
import { debugMode, emit } from "./voice/events";
import { VoiceDock } from "./voice/VoiceDock";

const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");
const DebugConsole = lazy(() => import("./voice/DebugConsole").then((m) => ({ default: m.DebugConsole })));

/** Signed-in screens: the sign-in screen first, in place, when signed out. */
function SignedIn() {
  const signedIn = useSession((s) => s.signedIn);
  const location = useLocation();
  if (signedIn) return <A.AppLayout />;
  return (
    <P.PublicLayout>
      <P.Login from={location.pathname} />
    </P.PublicLayout>
  );
}

/** Scroll to the top and tell the brain where the page is, on every route change. */
function useRouteEffects(path: string) {
  const signedIn = useSession((s) => s.signedIn);
  const first = useRef(true);
  useEffect(() => {
    if (!first.current) window.scrollTo(0, 0);
    first.current = false;
    emit("page_viewed", { path, screen: screenOf(path), signed_in: useSession.getState().signedIn });
  }, [path]);
  // A sign-in on a guarded screen changes what is on it without a route change.
  const was = useRef(signedIn);
  useEffect(() => {
    if (was.current === signedIn) return;
    was.current = signedIn;
    if (path.startsWith("/app")) emit("page_viewed", { path, screen: screenOf(path), signed_in: signedIn });
  }, [signedIn, path]);
}

function Shell() {
  const navigate = useNavigate();
  const location = useLocation();
  const path = useRef(location.pathname);
  path.current = location.pathname;
  useEffect(() => bindRouter((to, replace) => navigate(to, { replace }), () => path.current), [navigate]);
  const stage = useStageHost(location.pathname);
  usePerformers(stage);
  useRouteEffects(location.pathname);
  useDebugHarness();
  return (
    <>
      <Routes>
        <Route element={<P.PublicLayout />}>
          <Route index element={<P.Home />} />
          <Route path="login" element={<P.Login />} />
          <Route path="open-account" element={<P.OpenAccount />} />
          <Route path="cards" element={<P.CardsPage />} />
          <Route path="cards/compare" element={<P.CardsCompare />} />
          <Route path="cards/apply" element={<P.CardsApply />} />
          <Route path="cards/emi" element={<P.CardsEmi />} />
          <Route path="cards/:id" element={<P.CardDetail />} />
          <Route path="loans" element={<P.LoansPage />} />
          <Route path="loans/apply" element={<P.LoanApply />} />
          <Route path="loans/:type" element={<P.LoanPage />} />
          <Route path="*" element={<P.Home />} />
        </Route>
        <Route path="app" element={<SignedIn />}>
          <Route index element={<A.Dashboard />} />
          <Route path="accounts/:id" element={<A.AccountPage />} />
          <Route path="transactions" element={<A.Transactions />} />
          <Route path="insights" element={<A.Insights />} />
          <Route path="cards" element={<A.CardsHub />} />
          <Route path="cards/debit" element={<A.DebitCardPage />} />
          <Route path="cards/credit" element={<A.CreditCardPage />} />
          <Route path="payments" element={<A.Payments />} />
          <Route path="bills" element={<A.Bills />} />
          <Route path="deposits" element={<A.Deposits />} />
          <Route path="statements" element={<A.Statements />} />
          <Route path="offers" element={<A.Offers />} />
        </Route>
      </Routes>
      <ConfirmSheet />
      <VoiceDock />
      {debugMode() ? (
        <Suspense fallback={null}>
          <DebugConsole />
        </Suspense>
      ) : null}
    </>
  );
}

export function App() {
  return (
    <BrowserRouter basename={BASENAME}>
      <Shell />
    </BrowserRouter>
  );
}
