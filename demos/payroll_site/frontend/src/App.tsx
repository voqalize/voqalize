import { useEffect } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { BookDemo } from "./pages/BookDemo";
import { Customers } from "./pages/Customers";
import { Home } from "./pages/Home";
import { ModulePage } from "./pages/ModulePage";
import { Modules } from "./pages/Modules";
import { NotFound } from "./pages/NotFound";
import { Pricing } from "./pages/Pricing";
import { Tax } from "./pages/Tax";
import { StageHost } from "./stage/host";
import { DebugConsole } from "./voice/DebugConsole";
import { VoiceDock } from "./voice/VoiceDock";

const debug = () => new URLSearchParams(window.location.search).has("debug");

function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) window.scrollTo({ top: 0 });
  }, [pathname, hash]);
  return null;
}

export function App() {
  return (
    <BrowserRouter basename="/demos/payroll_site">
      <ScrollToTop />
      <StageHost />
      <Header />
      <main id="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/modules" element={<Modules />} />
          <Route path="/modules/:id" element={<ModulePage />} />
          <Route path="/tax" element={<Tax />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/book-demo" element={<BookDemo />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <Footer />
      <VoiceDock />
      {debug() ? <DebugConsole /> : null}
    </BrowserRouter>
  );
}
