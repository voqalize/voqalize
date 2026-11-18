/**
 * The public site: home, sign-in, account opening, cards and loans. Every page
 * root carries `data-stage-thing="screen:<screen>"`, which `nav.open` waits for.
 */
import type { ReactNode } from "react";
import { Outlet } from "react-router-dom";
import { Footer } from "../../components/Footer";
import { Header } from "../../components/Header";
import "../../styles/site.css";

export function PublicLayout({ children }: { children?: ReactNode }) {
  return (
    <div className="site">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <Header />
      <div id="main">{children ?? <Outlet />}</div>
      <Footer />
    </div>
  );
}

export { Home } from "./Home";
export { Login } from "./Login";
export { OpenAccount } from "./OpenAccount";
export { CardsPage, CardDetail, CardsCompare } from "./Cards";
export { CardsApply } from "./CardsApply";
export { CardsEmi } from "./CardsEmi";
export { LoansPage, LoanPage } from "./Loans";
export { LoanApply } from "./LoanApply";
