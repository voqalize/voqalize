import { Suspense, lazy, useEffect } from "react";
import { BrowserRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { ClaimPage } from "./pages/Claim";
import { ClaimSubmitted } from "./pages/ClaimSubmitted";
import { Home } from "./pages/Home";
import { MyPolicies } from "./pages/MyPolicies";
import { NotFound } from "./pages/NotFound";
import { PolicyDocument } from "./pages/PolicyDocument";
import { ProductPage } from "./pages/ProductPage";
import { QuotePage } from "./pages/QuotePage";
import { hello } from "./stage/host";
import { BASE, appPath, useUi } from "./state/ui";
import { VoiceDock } from "./voice/VoiceDock";
import { debugMode } from "./voice/debug";

const DebugConsole = lazy(() => import("./voice/DebugConsole"));

/** Hands the router to the performers, says hello on every route change, and scrolls to top. */
function RouterBinding() {
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    useUi.setState({ navigate: (to: string) => navigate(to) });
    return () => useUi.setState({ navigate: null });
  }, [navigate]);
  useEffect(() => {
    if (!location.hash) window.scrollTo({ top: 0, behavior: "auto" });
    hello();
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function Shell() {
  const location = useLocation();
  const path = location.pathname.replace(/\/+$/, "") || "/";
  return (
    <>
      <RouterBinding />
      <a className="skip" href="#main">
        Skip to content
      </a>
      <Header />
      <main id="main" data-stage-part={`page:${path}`}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/insurance/:product" element={<ProductPage />} />
          <Route path="/quote" element={<QuotePage />} />
          <Route path="/quote/:product" element={<QuotePage />} />
          <Route path="/my-policies" element={<MyPolicies />} />
          <Route path="/my-policies/:policyId" element={<PolicyDocument />} />
          <Route path="/claim" element={<ClaimPage />} />
          <Route path="/claim/submitted" element={<ClaimSubmitted />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <Footer />
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
    <BrowserRouter basename={BASE || "/"}>
      <Shell />
    </BrowserRouter>
  );
}

export { appPath };
