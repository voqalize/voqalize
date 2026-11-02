import { Suspense, lazy, useEffect, useRef } from "react";
import { BrowserRouter, Outlet, Route, Routes, useLocation, useNavigate, useNavigationType } from "react-router-dom";
import { useStageHost } from "./stage/host";
import { CartDrawer } from "./components/CartDrawer";
import { CircleLayer, fakeCircle } from "./components/CircleLayer";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { BriefBar, FloatingConfirm, PolicyPanel, ShortlistTray, Spotlight } from "./components/Overlays";
import { CartPage, CheckoutPage } from "./pages/Checkout";
import { ArticlePage, ConfirmationPage, ContactPage, InfoPage, JournalIndex, NotFound } from "./pages/Editorial";
import { Home } from "./pages/Home";
import { CategoryPage, RoomPage, SalePage, SearchPage, ShopPage } from "./pages/Listing";
import { BoardPage, ComparePage, PicksPage } from "./pages/EmilyViews";
import { ProductPage } from "./pages/ProductPage";
import { ReturnsConfirmation, ReturnsForm, ReturnsHome } from "./pages/Returns";
import { bindRouter, dispatch, emily, navigatedBy } from "./voice/controller";
import { useScreenReport } from "./voice/screen";
import { debugMode, emit } from "./voice/events";
import { VoiceDock } from "./voice/VoiceDock";

const DebugConsole = lazy(() => import("./voice/DebugConsole").then((m) => ({ default: m.DebugConsole })));
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");

/** Where each history entry was scrolled to, so Back lands where you left. */
const scrolls = new Map<string, number>();

function Shell() {
  const navigate = useNavigate();
  const location = useLocation();
  const navType = useNavigationType();
  const path = useRef(location.pathname);
  path.current = location.pathname;

  // Every move — a click, or Emily's navigate — is a history push through the router.
  useEffect(() => bindRouter((to) => navigate(to), () => path.current), [navigate]);
  useStageHost(location.pathname);
  useScreenReport(location.key);
  // Numbered choices belong to the screen they were shown on.
  useEffect(() => emily.clear_choices(), [location.pathname]);
  useEffect(() => {
    // Dev-only handle (?debug=1): fire a brain command from a test.
    if (debugMode()) {
      const w = window as unknown as { __fhDispatch?: typeof dispatch; __fhCircle?: typeof fakeCircle };
      w.__fhDispatch = dispatch;
      w.__fhCircle = fakeCircle;
    }
  }, []);

  // Scroll: top on a push, the remembered place on Back / Forward.
  useEffect(() => {
    try {
      window.history.scrollRestoration = "manual";
    } catch {
      /* older browsers */
    }
    let frame = 0;
    const remember = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => scrolls.set(location.key, window.scrollY));
    };
    window.addEventListener("scroll", remember, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", remember);
    };
  }, [location.key]);

  // A filter or sort on the same page replaces the URL in place: that is not a
  // new page, so no page_viewed, no scroll to the top, nothing cleared.
  const lastPath = useRef<string | null>(null);
  useEffect(() => {
    const samePage = lastPath.current === location.pathname && navType === "REPLACE";
    lastPath.current = location.pathname;
    if (samePage) return;
    emit("page_viewed", { path: location.pathname + location.search }, navigatedBy());
    if (location.hash) return;
    if (navType === "POP" && scrolls.has(location.key)) {
      const y = scrolls.get(location.key) ?? 0;
      // After the page below has rendered its content.
      requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo({ top: y })));
    } else {
      window.scrollTo({ top: 0 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key]);

  // Links inside rendered Markdown (articles, pages) route in the app too.
  const onClick = (e: React.MouseEvent) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = (e.target as Element).closest?.("a");
    if (!a || !a.closest(".prose") || a.target === "_blank") return;
    const to = internalPath(a.getAttribute("href") ?? "");
    if (to == null) return;
    e.preventDefault();
    navigate(to);
  };

  return (
    <div className="app" onClick={onClick}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Header />
      <BriefBar />
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
      <Footer />
      <CartDrawer />
      <ShortlistTray />
      <PolicyPanel />
      <FloatingConfirm />
      <Spotlight />
      <CircleLayer />
      <VoiceDock />
      {debugMode() ? (
        <Suspense fallback={null}>
          <DebugConsole />
        </Suspense>
      ) : null}
    </div>
  );
}

/** An href that stays in this store, as a router path; null for anything else. */
function internalPath(href: string): string | null {
  if (!href || href.startsWith("#") || /^(mailto|tel):/.test(href)) return null;
  let url: URL;
  try {
    url = new URL(href, window.location.href);
  } catch {
    return null;
  }
  if (url.origin !== window.location.origin) return null;
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  const p = url.pathname.startsWith(base) ? url.pathname.slice(base.length) || "/" : url.pathname;
  return `${p}${url.search}${url.hash}`;
}

export function App() {
  return (
    <BrowserRouter basename={BASENAME}>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route path="room/:room" element={<RoomPage />} />
          <Route path="category/:slug" element={<CategoryPage />} />
          <Route path="product/:id" element={<ProductPage />} />
          <Route path="shop" element={<ShopPage />} />
          <Route path="sale" element={<SalePage />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="picks" element={<PicksPage />} />
          <Route path="board" element={<BoardPage />} />
          <Route path="compare" element={<ComparePage />} />
          <Route path="cart" element={<CartPage />} />
          <Route path="checkout" element={<CheckoutPage />} />
          <Route path="checkout/confirmation" element={<ConfirmationPage />} />
          <Route path="journal" element={<JournalIndex />} />
          <Route path="journal/:slug" element={<ArticlePage />} />
          <Route path="about" element={<InfoPage slug="about" />} />
          <Route path="faq" element={<InfoPage slug="faq" />} />
          <Route path="policy/:topic" element={<InfoPage />} />
          <Route path="contact" element={<ContactPage />} />
          <Route path="returns" element={<ReturnsHome />} />
          <Route path="returns/start" element={<ReturnsForm />} />
          <Route path="returns/confirmation" element={<ReturnsConfirmation />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
