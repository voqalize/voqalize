import { Suspense, lazy, useEffect, useRef } from "react";
import { BrowserRouter, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { CallbackCard } from "./components/CallbackCard";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { Book } from "./pages/Book";
import { Home } from "./pages/Home";
import { MyAppointments } from "./pages/MyAppointments";
import { installDebugHook } from "./stage/debug";
import { useStageHost } from "./stage/host";
import { bindRouter, navigatedBy, pageOf } from "./stage/nav";
import { actions } from "./state/store";
import { debugMode, emit } from "./voice/events";
import { VoiceDock } from "./voice/VoiceDock";

const DebugConsole = lazy(() => import("./voice/DebugConsole").then((m) => ({ default: m.DebugConsole })));
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");

function Shell() {
  const navigate = useNavigate();
  const location = useLocation();
  const path = useRef(location.pathname);
  path.current = location.pathname;

  useEffect(() => bindRouter((to) => navigate(to), () => path.current), [navigate]);
  useStageHost(location.pathname);

  // The clock moves on: free times and "upcoming" follow it.
  useEffect(() => {
    const t = window.setInterval(() => actions.tick(), 30_000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (debugMode()) installDebugHook();
  }, []);

  useEffect(() => {
    emit("page_viewed", { page: pageOf(location.pathname), path: location.pathname }, navigatedBy());
    if (!location.hash) window.scrollTo({ top: 0 });
    // A sign-in panel or change sheet belongs to the page it opened on.
    actions.closeChange();
    actions.closePicker();
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

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
      <CallbackCard />
      <VoiceDock />
      {debugMode() ? (
        <Suspense fallback={null}>
          <DebugConsole />
        </Suspense>
      ) : null}
    </div>
  );
}

function NotFound() {
  return (
    <div className="wrap page-head" data-page="missing">
      <h1>That page isn't here</h1>
      <p className="muted">Try the home page, booking, or My appointments from the menu above.</p>
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter basename={BASENAME}>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route path="book" element={<Book />} />
          <Route path="my-appointments" element={<MyAppointments />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
