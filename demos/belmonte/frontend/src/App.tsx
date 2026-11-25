/**
 * Hotel Belmonte's guest app, in its phone.
 *
 * On a desktop or tablet the app runs inside an iPhone-style device frame on a
 * branded backdrop (`.frame`); on a real phone (narrow viewport) the frame's
 * chrome is gone and the app is the whole screen. Either way the app lives in
 * `#screen`, which is a containing block for everything fixed inside it
 * (`transform`), so the concierge's dock and call tile, the sheets and the
 * toast all stay inside the phone. The one scroll area is `#app-scroll`.
 */
import { Suspense, lazy, useEffect } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { Mark, StatusBar, TabBar, ToastHost } from "./components/Shell";
import { DATA, type ScenarioId } from "./data";
import { Activities } from "./pages/Activities";
import { CheckIn } from "./pages/CheckIn";
import { CheckOut } from "./pages/CheckOut";
import { Dining } from "./pages/Dining";
import { Home } from "./pages/Home";
import { Info } from "./pages/Info";
import { Meetings } from "./pages/Meetings";
import { Requests } from "./pages/Requests";
import { Spa } from "./pages/Spa";
import { Stay } from "./pages/Stay";
import { Visitors } from "./pages/Visitors";
import ActivitySheet from "./sheets/ActivitySheet";
import CartSheet from "./sheets/CartSheet";
import DisputeSheet from "./sheets/DisputeSheet";
import ExpectSheet from "./sheets/ExpectSheet";
import ItemSheet from "./sheets/ItemSheet";
import MeetingSheet from "./sheets/MeetingSheet";
import RequestSheet from "./sheets/RequestSheet";
import SpaSheet from "./sheets/SpaSheet";
import VisitorSheet from "./sheets/VisitorSheet";
import { StageHost } from "./stage/host";
import { pageOfPath } from "./stage/nav";
import { pageViewed, resetDemo, setScenario, useStay } from "./state/store";
import { debugMode } from "./voice/debug";
import { VoiceDock } from "./voice/VoiceDock";

const DebugConsole = lazy(() => import("./voice/DebugConsole"));

function PageWatch() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.getElementById("app-scroll")?.scrollTo({ top: 0 });
    pageViewed(pageOfPath(pathname));
  }, [pathname]);
  return null;
}

/** The open sheet, if any (one at a time). */
function SheetHost() {
  const sheet = useStay((s) => s.sheet);
  if (!sheet) return null;
  switch (sheet.kind) {
    case "item":
      return <ItemSheet sheet={sheet} />;
    case "cart":
      return <CartSheet sheet={sheet} />;
    case "spa":
      return <SpaSheet sheet={sheet} />;
    case "activity":
      return <ActivitySheet sheet={sheet} />;
    case "meeting":
      return <MeetingSheet sheet={sheet} />;
    case "visitor":
      return <VisitorSheet sheet={sheet} />;
    case "expect":
      return <ExpectSheet sheet={sheet} />;
    case "request":
      return <RequestSheet sheet={sheet} />;
    case "dispute":
      return <DisputeSheet sheet={sheet} />;
  }
}

/** The switch between the demo's two scenarios, and a reset. */
export function ScenarioSwitch() {
  const scenario = useStay((s) => s.scenario);
  return (
    <div className="scenario" role="group" aria-label="Demo scenario">
      <span className="scenario-label">Demo scenario</span>
      <div className="scenario-buttons">
        {(Object.keys(DATA.scenarios) as ScenarioId[]).map((id) => (
          <button key={id} type="button" aria-pressed={scenario === id} onClick={() => setScenario(id)}>
            {DATA.scenarios[id].label}
          </button>
        ))}
      </div>
      <button type="button" className="scenario-reset" onClick={resetDemo}>
        Reset demo
      </button>
    </div>
  );
}

function Backdrop() {
  return (
    <aside className="backdrop-copy">
      <div className="backdrop-brand">
        <Mark size={44} />
        <div>
          <p className="backdrop-name">Hotel Belmonte</p>
          <p className="backdrop-place">Halcyon Bay, California</p>
        </div>
      </div>
      <p className="backdrop-caption">Hotel Belmonte guest app, a Voqalize demo.</p>
      <p className="backdrop-lede">Everything a guest would phone the front desk for, done in the app, with a concierge who talks and drives the screen. Press Talk in the phone to start.</p>
      <ScenarioSwitch />
      <p className="backdrop-fine">Hotel Belmonte, its guests, menus, prices and policies are invented for this demo.</p>
    </aside>
  );
}

export function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
      <div className="frame">
        <Backdrop />
        <div className="device">
          <div className="device-buttons" aria-hidden />
          <div className="screen" id="screen">
            <StatusBar />
            <StageHost />
            <PageWatch />
            <div className="app-scroll" id="app-scroll">
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/dining" element={<Dining outlet="dining" />} />
                <Route path="/bar" element={<Dining outlet="bar" />} />
                <Route path="/spa" element={<Spa />} />
                <Route path="/activities" element={<Activities />} />
                <Route path="/meetings" element={<Meetings />} />
                <Route path="/requests" element={<Requests />} />
                <Route path="/visitors" element={<Visitors />} />
                <Route path="/stay" element={<Stay />} />
                <Route path="/stay/check-in" element={<CheckIn />} />
                <Route path="/stay/check-out" element={<CheckOut />} />
                <Route path="/info" element={<Info />} />
                <Route path="*" element={<Home />} />
              </Routes>
            </div>
            <TabBar />
            <SheetHost />
            <ToastHost />
            <VoiceDock />
            <div className="home-indicator" aria-hidden />
          </div>
        </div>
      </div>
      {debugMode() && (
        <Suspense fallback={null}>
          <DebugConsole />
        </Suspense>
      )}
    </BrowserRouter>
  );
}

