import { Suspense, lazy, useEffect, useRef } from "react";
import { BrowserRouter, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { CartDrawer } from "./components/CartDrawer";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { BriefBar, FloatingConfirm, PolicyPanel, ShortlistTray, Spotlight } from "./components/Overlays";
import { CartPage, CheckoutPage } from "./pages/Checkout";
import { ArticlePage, ConfirmationPage, ContactPage, InfoPage, JournalIndex, NotFound } from "./pages/Editorial";
import { Home } from "./pages/Home";
import { CategoryPage, RoomPage, SalePage, SearchPage, ShopPage } from "./pages/Listing";
import { BoardPage, ComparePage, PicksPage } from "./pages/MiraViews";
import { ProductPage } from "./pages/ProductPage";
import { bindRouter } from "./voice/controller";
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

  useEffect(() => {
    emit("page_viewed", { path: location.pathname + location.search });
    if (!location.hash) window.scrollTo({ top: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  return (
    <>
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
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
