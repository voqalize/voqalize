/** Authored admissions and campus-life content (`demos/university/data`). */
import adm from "../../../data/admissions.json";
import life from "../../../data/campus_life.json";

export interface Admissions {
  process: { step: number; title: string; text: string }[];
  vusat: { name: string; format: string; phases: { name: string; dates: string; register_by: string }[]; note: string };
  fees: {
    what_is_included: string;
    one_time: { item: string; amount: number; refundable: boolean }[];
    seat_confirmation: string;
    instalments: string;
    zero_interest_plan: string;
    refund: string;
    payment_methods: string;
  };
  hostel: {
    summary: string;
    rooms: { id: string; campus: string; label: string; per_year: number }[];
    deposit: number;
    allotment: string;
    rules: string;
  };
  loans: { summary: string; covers: string; timeline: string; who_decides: string; contact: string };
  scholarship_rules: string[];
  documents: { id: string; label: string; for: string }[];
  faqs: { q: string; a: string }[];
  contact: { phone: string; email: string; hours: string; whatsapp: string };
}

export interface CampusLife {
  stats: { label: string; value: string }[];
  sections: { id: string; title: string; text: string }[];
}

export const ADMISSIONS = adm as unknown as Admissions;
export const CAMPUS_LIFE = life as unknown as CampusLife;
