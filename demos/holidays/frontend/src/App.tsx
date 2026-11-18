import { Suspense, lazy, useEffect } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { Footer, Header } from "./components/Chrome";
import { Booked } from "./pages/Booked";
import { Checkout } from "./pages/Checkout";
import { Home } from "./pages/Home";
import { Plan } from "./pages/Plan";
import { StageHost } from "./stage/host";
import { pageViewed } from "./state/trip";
import { VoiceDock } from "./voice/VoiceDock";
import { debugMode } from "./voice/debug";

const DebugConsole = lazy(() => import("./voice/DebugConsole"));

function PageWatch() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0 });
    const p = pathname.replace(/\/$/, "").split("/").pop() || "home";
    pageViewed(["plan", "checkout", "booked"].includes(p) ? p : "home");
  }, [pathname]);
  return null;
}

export function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
      <StageHost />
      <PageWatch />
      <Header />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/plan" element={<Plan />} />
          <Route path="/checkout" element={<Checkout />} />
          <Route path="/booked" element={<Booked />} />
          <Route path="*" element={<Home />} />
        </Routes>
      </main>
      <Footer />
      <VoiceDock />
      {debugMode() && (
        <Suspense fallback={null}>
          <DebugConsole />
        </Suspense>
      )}
    </BrowserRouter>
  );
}
