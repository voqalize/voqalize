import { Bike, Car, HeartPulse, Home as HomeIcon, Plane, ShieldPlus } from "lucide-react";
import type { ComponentType } from "react";
import type { ProductId } from "../data/types";
import { persona } from "../persona";
import portrait from "../assets/portrait.png";

export const PRODUCT_ICON: Record<ProductId, ComponentType<{ size?: number; strokeWidth?: number; "aria-hidden"?: boolean }>> = {
  car: Car,
  bike: Bike,
  health: HeartPulse,
  term: ShieldPlus,
  home: HomeIcon,
  travel: Plane,
};

export const PRODUCT_BLURB: Record<ProductId, string> = {
  car: "Comprehensive cover with zero depreciation, engine protection and 24x7 roadside help.",
  bike: "Scooters and motorcycles, with owner-rider accident cover built in.",
  health: "Family floater or individual, with cashless care at network hospitals.",
  term: "Pure life cover for your family, at a fixed yearly premium.",
  home: "Your building and what’s inside it, against fire, flood and burglary.",
  travel: "Medical cover abroad, baggage, delays and trip cancellation.",
};

export function ProductIcon({ product, size = 22 }: { product: ProductId; size?: number }) {
  const I = PRODUCT_ICON[product];
  return <I size={size} strokeWidth={1.7} aria-hidden />;
}

export function Portrait({ className }: { className?: string }) {
  return <img className={className} src={portrait} alt={`${persona.name}, ${persona.role}`} />;
}

export function KindBadge({ kind }: { kind: string }) {
  const LABEL: Record<string, string> = {
    covered: "Covered",
    excluded: "Excluded",
    limit: "Limit",
    waiting: "Waiting period",
    copay: "Co-pay",
    deductible: "Deductible",
    condition: "Condition",
    info: "Definition",
  };
  return <span className={`kind kind-${kind}`}>{LABEL[kind] ?? kind}</span>;
}
