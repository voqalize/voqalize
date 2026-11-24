import { Building2, Calendar, FileCheck, Landmark, Plug, Receipt, ReceiptIndianRupee, Shield, Users, Wallet } from "lucide-react";
import type { ComponentType } from "react";

const ICONS: Record<string, ComponentType<{ size?: number; strokeWidth?: number }>> = {
  wallet: Wallet,
  users: Users,
  calendar: Calendar,
  receipt: Receipt,
  landmark: Landmark,
  shield: Shield,
  "receipt-indian-rupee": ReceiptIndianRupee,
  "file-check": FileCheck,
  building: Building2,
  plug: Plug,
};

export function ModuleIcon({ name, size = 20 }: { name: string; size?: number }) {
  const Icon = ICONS[name] ?? Wallet;
  return <Icon size={size} strokeWidth={1.75} />;
}
