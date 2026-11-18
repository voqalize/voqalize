import { Suspense, lazy, useEffect, useRef } from "react";
import { BrowserRouter, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { Admissions } from "./pages/Admissions";
import { Apply } from "./pages/Apply";
import { CampusLife } from "./pages/CampusLife";
import { Home } from "./pages/Home";
import { NotFound } from "./pages/NotFound";
import { ProgramPage } from "./pages/ProgramPage";
import { Programs } from "./pages/Programs";
import { Scholarships } from "./pages/Scholarships";
import { SchoolPage, Schools } from "./pages/Schools";
import { announce, bindRouter, moves, runByHand } from "./stage/host";
import { registerPerformers } from "./stage/performers";
import { startReporting } from "./stage/report";
import { debugMode, rememberDebug } from "./voice/debug";
import { VoiceDock } from "./voice/VoiceDock";

// One Moves for the app's life: every performer registered once, every
// state change reported, with or without a call.
registerPerformers();
startReporting();
rememberDebug();

const DebugConsole = lazy(() => import("./voice/DebugConsole").then((m) => ({ default: m.DebugConsole })));
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");

function Shell() {
  const navigate = useNavigate();
  const location = useLocation();
  const path = useRef(location.pathname);
  path.current = location.pathname;

  useEffect(() => bindRouter((to) => navigate(to), () => path.current), [navigate]);
  useEffect(() => {
    if (!debugMode()) return;
    (window as unknown as { __anvaya?: unknown }).__anvaya = { moves, run: runByHand };
  }, []);

  // Every route change: the brain switches job on the hello's path.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
    } else {
      announce();
    }
    if (!location.hash) window.scrollTo({ top: 0 });
  }, [location.pathname]);

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Header />
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
      <Footer />
      <VoiceDock />
      {debugMode() ? (
        <Suspense fallback={null}>
          <DebugConsole />
        </Suspense>
      ) : null}
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter basename={BASENAME}>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route path="programs" element={<Programs />} />
          <Route path="programs/:id" element={<ProgramPage />} />
          <Route path="schools" element={<Schools />} />
          <Route path="schools/:id" element={<SchoolPage />} />
          <Route path="admissions" element={<Admissions />} />
          <Route path="scholarships" element={<Scholarships />} />
          <Route path="campus-life" element={<CampusLife />} />
          <Route path="apply" element={<Apply />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
