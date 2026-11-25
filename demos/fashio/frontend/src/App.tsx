import { Suspense, lazy, useEffect, useRef } from "react";
import { BrowserRouter, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { logicalPath, toUrl } from "./data/catalog";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { About } from "./pages/About";
import { BagPage } from "./pages/Bag";
import { Checkout } from "./pages/Checkout";
import { Compare } from "./pages/Compare";
import { Gifts } from "./pages/Gifts";
import { Home } from "./pages/Home";
import { Kiosk } from "./pages/Kiosk";
import { NotFound } from "./pages/NotFound";
import { Orders } from "./pages/Orders";
import { ProductPage } from "./pages/ProductPage";
import { Returns } from "./pages/Returns";
import { Shop } from "./pages/Shop";
import { Wishlist } from "./pages/Wishlist";
import { bindRouter, runByHand } from "./stage/host";
import "./stage/performers";
import { useStageReport } from "./stage/report";
import { VoiceDock } from "./voice/VoiceDock";

const DebugConsole = lazy(() => import("./voice/DebugConsole").then((m) => ({ default: m.DebugConsole })));
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");
export const debugMode = () => {
  try {
    return new URLSearchParams(window.location.search).has("debug") || sessionStorage.getItem("fashio-debug") === "1";
  } catch {
    return false;
  }
};

function Shell() {
  const navigate = useNavigate();
  const location = useLocation();
  // Performers and the brain name a product page /p/<id>; its URL is /p/?id=<id>.
  const logical = logicalPath(location.pathname, location.search);
  const path = useRef(logical);
  path.current = logical;
  useEffect(() => bindRouter((to) => navigate(toUrl(to)), () => path.current), [navigate]);
  useStageReport(logical, location.search);
  if (new URLSearchParams(location.search).has("debug")) {
    try {
      sessionStorage.setItem("fashio-debug", "1");
    } catch {
      /* storage unavailable */
    }
  }
  const debug = debugMode();
  useEffect(() => {
    if (debug) (window as unknown as { __fashio?: unknown }).__fashio = { run: runByHand };
  }, [debug]);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [logical]);
  // The kiosk is a full-screen in-store screen: no store header or footer.
  const kiosk = location.pathname.startsWith("/kiosk");
  return (
    <>
      {kiosk ? null : <Header />}
      <main id="main" className={kiosk ? "is-kiosk" : undefined}>
        <Outlet />
      </main>
      {kiosk ? null : <Footer />}
      <VoiceDock />
      {debug ? (
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
          <Route path="shop" element={<Shop />} />
          <Route path="shop/:dept" element={<Shop />} />
          <Route path="shop/:dept/:type" element={<Shop />} />
          <Route path="p" element={<ProductPage />} />
          <Route path="p/:id" element={<ProductPage />} />
          <Route path="compare" element={<Compare />} />
          <Route path="wishlist" element={<Wishlist />} />
          <Route path="bag" element={<BagPage />} />
          <Route path="checkout" element={<Checkout />} />
          <Route path="about" element={<About />} />
          <Route path="gifts" element={<Gifts />} />
          <Route path="orders" element={<Orders />} />
          <Route path="returns" element={<Returns />} />
          <Route path="kiosk" element={<Kiosk />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
