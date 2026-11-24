import { Suspense, lazy, useEffect, useRef } from "react";
import { BrowserRouter, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Footer, Header } from "./components/Chrome";
import { Home } from "./pages/Home";
import { ListingPage } from "./pages/ListingPage";
import { ListingsPage } from "./pages/Listings";
import { ComparePage, NotFound, ProjectPage, ShortlistPage, VisitsPage } from "./pages/Misc";
import { bindRouter, runByHand } from "./stage/host";
import "./stage/performers";
import { useStageReport } from "./stage/report";
import { VoiceDock } from "./voice/VoiceDock";

const DebugConsole = lazy(() => import("./voice/DebugConsole").then((m) => ({ default: m.DebugConsole })));
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");
export const debugMode = () => new URLSearchParams(window.location.search).has("debug") || sessionStorage.getItem("kosha-debug") === "1";

function Shell() {
  const navigate = useNavigate();
  const location = useLocation();
  const path = useRef(location.pathname);
  path.current = location.pathname;
  useEffect(() => bindRouter((to) => navigate(to), () => path.current), [navigate]);
  useStageReport(location.pathname, location.search.includes("ids=") ? location.search : "");
  const debug = useRef(false);
  if (new URLSearchParams(location.search).has("debug")) {
    try {
      sessionStorage.setItem("kosha-debug", "1");
    } catch {
      /* storage unavailable */
    }
  }
  debug.current = debugMode();
  useEffect(() => {
    if (debug.current) (window as unknown as { __kosha?: unknown }).__kosha = { run: runByHand };
  }, []);
  useEffect(() => {
    if (location.hash) {
      document.querySelector(location.hash)?.scrollIntoView({ behavior: "smooth" });
    } else {
      window.scrollTo(0, 0);
    }
  }, [location.pathname, location.hash]);
  return (
    <>
      <Header />
      <main id="main">
        <Outlet />
      </main>
      <Footer />
      <VoiceDock />
      {debug.current ? (
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
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route path="listings" element={<ListingsPage />} />
          <Route path="listing/:id" element={<ListingPage />} />
          <Route path="project/:id" element={<ProjectPage />} />
          <Route path="compare" element={<ComparePage />} />
          <Route path="shortlist" element={<ShortlistPage />} />
          <Route path="visits" element={<VisitsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
