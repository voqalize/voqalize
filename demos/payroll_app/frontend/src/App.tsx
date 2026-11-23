import { Suspense, lazy, useEffect, useLayoutEffect, useRef } from "react";
import { BrowserRouter, Link, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { screenOf } from "./lib/routes";
import { bindRouter, withSlash } from "./state/nav";
import { useTk } from "./state/store";
import { emit, hello } from "./stage/runtime";
import { debugMode } from "./voice/debug";
import { VoiceDock } from "./voice/VoiceDock";
import { Shell } from "./components/Shell";
import { HandoffDrawer } from "./components/Handoff";
import { PageHead } from "./components/ui";
import { Dashboard } from "./pages/Dashboard";
import { EmployeeDetail, EmployeeNew, EmployeesList } from "./pages/Employees";
import { PayrollRun, PayrollRuns } from "./pages/Payroll";
import { PayslipPage, PayslipsIndex } from "./pages/Payslips";
import { LeavePage } from "./pages/Leave";
import { ReimbursementsPage } from "./pages/Reimbursements";
import { RegimePage, TaxPage } from "./pages/Tax";
import { SettingsPage } from "./pages/Settings";
import { HelpPage } from "./pages/Help";
import { MePage } from "./pages/Me";
import { WelcomePage } from "./pages/Welcome";

const DebugConsole = lazy(() => import("./voice/DebugConsole").then((m) => ({ default: m.DebugConsole })));
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");

function Frame() {
  const navigate = useNavigate();
  const loc = useLocation();
  const here = useRef(loc.pathname + loc.search);
  here.current = loc.pathname + loc.search;
  useLayoutEffect(() => {
    const fixed = withSlash(window.location.pathname);
    if (fixed) window.history.replaceState(window.history.state, "", fixed + window.location.search + window.location.hash);
  }, [loc.pathname, loc.search, loc.hash]);
  useEffect(() => bindRouter((to, o) => navigate(to, o), () => here.current), [navigate]);

  // Every route change: the tab title, `screen.viewed` (silent) and a fresh hello.
  useEffect(() => {
    const s = screenOf(loc.pathname, loc.search);
    document.title = `${s.title}, ${"Paynora"}`;
    emit("screen.viewed", s);
    hello();
    window.scrollTo({ top: 0 });
  }, [loc.pathname, loc.search]);

  const me = loc.pathname.startsWith("/me/");
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      {me ? <Outlet /> : <Shell>{<Outlet />}</Shell>}
      <Notices />
      <HandoffDrawer />
      <VoiceDock />
      {debugMode() ? (
        <Suspense fallback={null}>
          <DebugConsole />
        </Suspense>
      ) : null}
    </>
  );
}

function Notices() {
  const notices = useTk((s) => s.notices);
  return (
    <div className="notices" aria-live="polite">
      {notices.map((n) => (
        <p key={n.id} className={`notice notice-${n.tone}`}>
          {n.text}
        </p>
      ))}
    </div>
  );
}

function NotFound() {
  return (
    <div className="page">
      <PageHead title="Page not found" sub="This address is not a page in Paynora." />
      <Link to="/" className="btn btn-primary">
        Go to the dashboard
      </Link>
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter basename={BASENAME}>
      <Routes>
        <Route element={<Frame />}>
          <Route index element={<Dashboard />} />
          <Route path="welcome" element={<WelcomePage />} />
          <Route path="employees" element={<EmployeesList />} />
          <Route path="employees/new" element={<EmployeeNew />} />
          <Route path="employees/:id" element={<EmployeeDetail />} />
          <Route path="payroll" element={<PayrollRuns />} />
          <Route path="payroll/:runId" element={<PayrollRun />} />
          <Route path="payslips" element={<PayslipsIndex />} />
          <Route path="payslips/:employeeId/:month" element={<PayslipPage />} />
          <Route path="leave" element={<LeavePage />} />
          <Route path="reimbursements" element={<ReimbursementsPage />} />
          <Route path="tax" element={<TaxPage />} />
          <Route path="tax/regime/:employeeId" element={<RegimePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="help" element={<HelpPage />} />
          <Route path="me/:employeeId" element={<MePage />} />
          <Route path="me/:employeeId/:tab" element={<MePage />} />
          <Route path="me/:employeeId/:tab/:month" element={<MePage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
