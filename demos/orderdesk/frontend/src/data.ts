/**
 * Scenario data for OrderDesk — 2 pharmacies × 3 day-scenarios (DESIGN.md §6).
 *
 * Every product reference below is a REAL row from the 20,148-SKU Enterro
 * catalog (grepped by hand, code + clean name + pack size copied verbatim,
 * trailing "-<CODE>" suffix stripped from Product_Name). No invented SKUs.
 *
 * The arcs:
 *   Gupta Medical Store (Delhi, chronic-heavy, high volume, est. customer) —
 *     Day 1 clean happy-path order, Day 2 the ambiguity day (VOLINI pack/
 *     variant, 4 QUIN drops-vs-ointment, THYRONORM strength, ABEVIA/ABIWAYS
 *     phonetic pair), Day 3 "mera regular order" reorder with two mid-call
 *     corrections.
 *   New Sanjivani Pharmacy (Pune, OTC/derm-heavy, brand-new account) —
 *     Day 1 onboarding order (small, clean), Day 2 pack-size + scheme day
 *     (items with a real non-empty Scheme column), Day 3 momentum: a bigger
 *     order, one item that is genuinely not in the catalog, and one
 *     presenter-driven manual-search add.
 *
 * `buildBrainPayload` folds a scenario + its pharmacy into the single JSON
 * object that rides the session payload to the `orderdesk` brain (DESIGN §4).
 */

import type { Pharmacy, Scenario } from "./types";

// ── Pharmacies ───────────────────────────────────────────────────────────────

export const PHARMACIES: Pharmacy[] = [
  {
    id: "gupta",
    name: "Gupta Medical Store",
    owner: "Ramesh Gupta",
    city: "Delhi",
    area: "Karol Bagh",
    since: "Customer since 2014",
    volume_line: "₹4.2L / month · ~30 orders",
    credit_line: "21-day credit · clean record",
    tags: ["chronic-heavy", "high volume"],
    hue: 215,
  },
  {
    id: "sanjivani",
    name: "New Sanjivani Pharmacy",
    owner: "Priya Deshmukh",
    city: "Pune",
    area: "Kothrud",
    since: "Customer since 2026",
    volume_line: "₹85K / month · ~10 orders",
    credit_line: "7-day credit · new account",
    tags: ["newer store", "OTC/derm-heavy"],
    hue: 32,
  },
];

export function pharmacyById(id: string): Pharmacy {
  return PHARMACIES.find((p) => p.id === id) ?? PHARMACIES[0];
}

// ── Scenarios ────────────────────────────────────────────────────────────────

export const SCENARIOS: Scenario[] = [
  // ── Gupta Medical Store ─────────────────────────────────────────────────

  {
    id: "gupta-d1",
    pharmacy_id: "gupta",
    day_label: "Day 1",
    title: "The first morning call",
    call_type: "first_order",
    chip: "Happy path",
    context_bullets: [
      "12-year customer, high-volume chronic-therapy counter",
      "Predictable weekday order pattern, clean 21-day credit record",
      "No open issues from last week — routine Monday call",
      "Goal: take today's order end to end, everything should resolve cleanly",
    ],
    try_hints: [
      "Telma forty de do, tees strip",
      "Shelcal five hundred, bees strip",
      "Pan forty, chaalis strip",
      "Dolo six fifty, pachaas strip",
      "Augmentin six two five duo, bees strip",
      "Bas itna hi aaj, confirm kar do",
    ],
    prior_calls: [
      {
        day: "Last Monday",
        summary:
          "Routine weekly order — Telma 40, Shelcal-500, Pan 40, Dolo 650, Augmentin 625 Duo, all clean matches. Delivered same day, no complaints.",
        commitment: "Same basket most Mondays",
      },
    ],
    order_history: [
      { sku_code: "J0031270", name: "TELMA 40 TABLET", pack_size: "15'S", qty: 30, when: "last Monday" },
      { sku_code: "J0029359", name: "SHELCAL-500 TABLET", pack_size: "15'S", qty: 20, when: "last Monday" },
      { sku_code: "J0024991", name: "PAN 40 TABLET", pack_size: "15'S", qty: 40, when: "last Monday" },
      { sku_code: "J0010291", name: "DOLO-650 TABLET", pack_size: "15'S", qty: 50, when: "last Monday" },
      { sku_code: "J0004502", name: "AUGMENTIN 625 DUO TABLET", pack_size: "10'S", qty: 20, when: "last Monday" },
      { sku_code: "J0014899", name: "GLYCOMET 500 MG TABLET", pack_size: "10'S", qty: 25, when: "last Monday" },
      { sku_code: "J0038288", name: "THYRONORM 50 MCG TABLET", pack_size: "120'S", qty: 10, when: "last Monday" },
    ],
    usual_items: [],
    objective:
      "FIRST ORDER OF THE WEEK — clean happy path. Ramesh will call out five or six well-known chronic-therapy brands with quantities, one after another: Telma 40, Shelcal-500, Pan 40, Dolo 650, Augmentin 625 Duo. Every one of these should resolve to a single SKU without any clarifying question — this call is the baseline the ambiguity day (tomorrow) will contrast against. Keep taking items while earlier ones resolve, don't slow him down. Once everything is matched, prompt him to press Confirm.",
    nudge: "Good morning Ramesh ji! Aaj ka order lagayein — one tap on MedSetu.",
  },
  {
    id: "gupta-d2",
    pharmacy_id: "gupta",
    day_label: "Day 2",
    title: "The ambiguity day",
    call_type: "ambiguous_day",
    chip: "Ambiguity day",
    context_bullets: [
      "Yesterday's order delivered clean — Telma, Shelcal, Pan, Dolo, Augmentin",
      "Today's basket leans pain-relief and eye-care — expect bare brand names with no pack/form/strength",
      "Two MANKIND brands on this line sound alike — probe carefully before locking a SKU",
      "Goal: resolve every ambiguous item to a single SKU with one short question each",
    ],
    try_hints: [
      "Volini de do",
      "Pachaas gram wala Joint Xpert de do",
      "Chaar Quin chahiye",
      "Drops wala do",
      "Thyronorm chahiye",
      "Abeviya... nahi nahi, Abiways chahiye",
    ],
    prior_calls: [
      {
        day: "Day 1 — Mon",
        summary:
          "First order of the week — Telma 40, Shelcal-500, Pan 40, Dolo 650, Augmentin 625 Duo, all clean matches, confirmed and delivered same day.",
        commitment: "Same basket most Mondays",
      },
    ],
    order_history: [
      { sku_code: "J0031270", name: "TELMA 40 TABLET", pack_size: "15'S", qty: 30, when: "yesterday" },
      { sku_code: "J0029359", name: "SHELCAL-500 TABLET", pack_size: "15'S", qty: 20, when: "yesterday" },
      { sku_code: "J0024991", name: "PAN 40 TABLET", pack_size: "15'S", qty: 40, when: "yesterday" },
      { sku_code: "J0010291", name: "DOLO-650 TABLET", pack_size: "15'S", qty: 50, when: "yesterday" },
      { sku_code: "J0004502", name: "AUGMENTIN 625 DUO TABLET", pack_size: "10'S", qty: 20, when: "yesterday" },
      { sku_code: "J0014899", name: "GLYCOMET 500 MG TABLET", pack_size: "10'S", qty: 25, when: "yesterday" },
      { sku_code: "J0038288", name: "THYRONORM 50 MCG TABLET", pack_size: "120'S", qty: 10, when: "yesterday" },
    ],
    usual_items: [],
    objective:
      "AMBIGUITY DAY. Ramesh will name brands with nothing else — no pack size, no form, no strength. \"Volini\" alone is a 10-SKU family (gel 100gm/75gm, joint xpert, maxx spray, pain relief gel/spray) — ask ONE short question about whatever axis actually differs, point at the screen, don't read the list aloud. \"4 Quin\" is one family with both eye drops and eye ointment — ask drops-or-ointment. \"Thyronorm\" alone spans eight strengths — ask which strength, or wait for him to say it unprompted. If he says something that sounds like ABEVIA or ABIWAYS, don't guess — these are two different real MANKIND brands (one a capsule, one a tablet with a scheme) and sound alike over a phone line; ask him to repeat or confirm which one before locking a SKU. Keep the cart moving — batch questions at natural pauses rather than interrogating him after every item.",
    nudge: "Volini aur eye-care line ka stock bharna hai aaj — join the MedSetu call, Gupta ji.",
  },
  {
    id: "gupta-d3",
    pharmacy_id: "gupta",
    day_label: "Day 3",
    title: "The regular reorder",
    call_type: "reorder",
    chip: "Reorder",
    context_bullets: [
      "Wednesday call — asks for his \"regular order\" most weeks, same seven-line basket",
      "Yesterday's ambiguous items (Volini, 4 Quin, Thyronorm) all resolved and delivered",
      "Expect at least one quantity correction mid-call — normal for him",
      "Goal: reorder from history in one shot, handle corrections cleanly, confirm",
    ],
    try_hints: [
      "Mera regular order laga do",
      "Telma forty — tees nahi, baarah kar do",
      "Volini gel bhi jod do, sau gram wala",
      "Volini hata do",
      "Thyronorm ki pandrah strip kar do",
      "Bas itna hi, confirm kar do",
    ],
    prior_calls: [
      {
        day: "Day 1 — Mon",
        summary:
          "First order of the week — Telma 40, Shelcal-500, Pan 40, Dolo 650, Augmentin 625 Duo, all clean matches, confirmed and delivered same day.",
        commitment: "Same basket most Mondays",
      },
      {
        day: "Day 2 — Tue",
        summary:
          "Ambiguity day. Volini resolved to Joint Xpert 50gm, 4 Quin resolved to eye drops, Thyronorm resolved to 50 mcg. One near-miss between Abevia and Abiways, caught before confirming — he wanted Abiways.",
        commitment: "Confirm his usual seven-line basket by voice going forward",
      },
    ],
    order_history: [
      { sku_code: "J0031270", name: "TELMA 40 TABLET", pack_size: "15'S", qty: 30, when: "most weeks" },
      { sku_code: "J0029359", name: "SHELCAL-500 TABLET", pack_size: "15'S", qty: 20, when: "most weeks" },
      { sku_code: "J0024991", name: "PAN 40 TABLET", pack_size: "15'S", qty: 40, when: "most weeks" },
      { sku_code: "J0010291", name: "DOLO-650 TABLET", pack_size: "15'S", qty: 50, when: "most weeks" },
      { sku_code: "J0004502", name: "AUGMENTIN 625 DUO TABLET", pack_size: "10'S", qty: 20, when: "most weeks" },
      { sku_code: "J0014899", name: "GLYCOMET 500 MG TABLET", pack_size: "10'S", qty: 25, when: "most weeks" },
      { sku_code: "J0038288", name: "THYRONORM 50 MCG TABLET", pack_size: "120'S", qty: 10, when: "most weeks" },
    ],
    usual_items: [
      "Telma 40",
      "Shelcal-500",
      "Pan 40",
      "Dolo 650",
      "Augmentin 625 Duo",
      "Glycomet 500",
      "Thyronorm 50 mcg",
    ],
    objective:
      "REORDER DAY. Ramesh will most likely open with \"mera regular order laga do\" — when he does, add his usual seven-line basket from order history in one add_items call rather than asking him to repeat each item. Expect at least one mid-call correction on quantity (he changes his mind on Telma's strip count) — use set_quantity, don't re-add. He may also ask for one extra item beyond the usual basket and then remove it — use remove_items, acknowledge without fuss, don't re-litigate. Once the cart is settled and everything is matched, prompt him to confirm.",
    nudge: "Budhwar ka order taiyaar hai? Tap karein aur bata dein, Gupta ji.",
  },

  // ── New Sanjivani Pharmacy ───────────────────────────────────────────────

  {
    id: "sanjivani-d1",
    pharmacy_id: "sanjivani",
    day_label: "Day 1",
    title: "The onboarding order",
    call_type: "first_order",
    chip: "Onboarding",
    context_bullets: [
      "New account, onboarded this month by the area sales rep",
      "First-ever voice order — this is her introduction to how MedSetu calls work",
      "Small mixed OTC/derm basket expected, not chronic-heavy like Gupta's counter",
      "Goal: a smooth first order, build confidence in the flow",
    ],
    try_hints: [
      "Crocin six fifty, bees strip de do",
      "Dolo six fifty bhi chahiye, tees strip",
      "Volini gel pichhattar gram wala, pandrah piece",
      "Candid cream das piece de do",
      "Itch Guard cream bhi das piece",
      "Liv fifty-two syrup das bottle, bas itna hi",
    ],
    prior_calls: [],
    order_history: [],
    usual_items: [],
    objective:
      "ONBOARDING CALL — first-ever voice order for Priya's store. Open warm and brief: this is a new relationship, so a one-line explanation of how the call works (she talks, items land on screen, she confirms manually) is welcome before diving in. She'll order a small, mixed OTC/derm basket — Crocin 650, Dolo 650, Volini Gel, Candid Cream, Itch Guard Plus Cream, Liv 52 Syrup — with brand + pack + quantity spoken together most of the time, so matches should be clean. Keep the pace unhurried, this is about building confidence in the flow, not speed. Close by confirming the order and telling her you'll call again tomorrow.",
    nudge: "Namaste Priya ji! Aapka pehla MedSetu order tayyar hai — tap karke jodiye.",
  },
  {
    id: "sanjivani-d2",
    pharmacy_id: "sanjivani",
    day_label: "Day 2",
    title: "Pack-size and scheme day",
    call_type: "scheme_day",
    chip: "Scheme day",
    context_bullets: [
      "Second order — comfortable with the call now",
      "Several items on today's list carry active supplier schemes this week",
      "VOLINI comes in more than one pack/size she stocks — confirm which before locking",
      "Goal: surface every scheme deal out loud, resolve pack sizes without fuss",
    ],
    try_hints: [
      "Four PCOS chahiye",
      "Four U Q ten bhi de do",
      "Volini gel de do, bada wala",
      "Volini Maxx spray bhi chahiye",
      "Pan MPS syrup ek bottle",
      "Bas, aaj ka order itna hi",
    ],
    prior_calls: [
      {
        day: "Day 1",
        summary:
          "First voice order — Crocin 650, Dolo 650, Volini Gel 75gm, Candid Cream, Itch Guard Plus Cream, Liv 52 Syrup, all confirmed. She said the call felt easier than she expected.",
        commitment: "Call again the next day, keep it short",
      },
    ],
    order_history: [
      { sku_code: "J0042294", name: "CROCIN 650 TABLET", pack_size: "1*15", qty: 20, when: "Day 1" },
      { sku_code: "J0010291", name: "DOLO-650 TABLET", pack_size: "15'S", qty: 30, when: "Day 1" },
      { sku_code: "J0034539", name: "VOLINI GEL", pack_size: "75GM", qty: 15, when: "Day 1" },
      { sku_code: "J0006463", name: "CANDID CREAM", pack_size: "50GM", qty: 10, when: "Day 1" },
      { sku_code: "J0016849", name: "ITCH GUARD PLUS CREAM", pack_size: "20GM", qty: 10, when: "Day 1" },
      { sku_code: "J0018841", name: "LIV 52 SYRUP", pack_size: "200ML", qty: 10, when: "Day 1" },
      { sku_code: "J0009625", name: "DETTOL ANTI SEPTIC LIQUID", pack_size: "250ML", qty: 8, when: "Day 1" },
    ],
    usual_items: [],
    objective:
      "SCHEME DAY. Several items Priya orders today carry a real supplier scheme this week — 4PCOS (5+1), 4U-Q10 (10+1), Volini Maxx Spray but ONLY the 55gm pack (4+1) not the 25gm, Pan MPS Syrup (5+1). Whenever an item resolves and it carries a scheme, say the deal out loud in one short line and let the screen show the badge — don't bury it. Volini Gel comes in two pack sizes she stocks both of (100gm and 75gm) — when she just says \"volini gel\" without a size, ask which, options are on screen. 4U-Q10 also has a plain and a \"plus\" variant — only the plain one carries the scheme, so confirm which she means before locking it in. Close once everything is matched and confirm.",
    nudge: "Scheme chal rahi hai kuch items par aaj — join the MedSetu call, Priya ji.",
  },
  {
    id: "sanjivani-d3",
    pharmacy_id: "sanjivani",
    day_label: "Day 3",
    title: "Momentum",
    call_type: "momentum",
    chip: "Momentum",
    context_bullets: [
      "Third call — bigger order this week, more lines than usual",
      "One item she'll ask for isn't in the catalog — search bar is the fallback",
      "Comfortable enough now to try the manual search herself",
      "Goal: handle a bigger basket smoothly, don't stumble on the not-found item, confirm",
    ],
    try_hints: [
      "Crocin six fifty, tees strip de do",
      "Dolo six fifty bhi tees strip",
      "Volini gel pichhattar gram wala, bees piece",
      "Coldact bhi de do",
      "Type 'cetaphil lotion' in the search bar — show the manual add",
      "Shelcal five hundred bhi jod do, pandrah strip — bas, confirm kar do",
    ],
    prior_calls: [
      {
        day: "Day 1",
        summary:
          "First voice order — Crocin 650, Dolo 650, Volini Gel 75gm, Candid Cream, Itch Guard Plus Cream, Liv 52 Syrup, all confirmed. She said the call felt easier than she expected.",
        commitment: "Call again the next day, keep it short",
      },
      {
        day: "Day 2",
        summary:
          "Scheme day. 4PCOS, 4U-Q10, Volini Maxx Spray 55gm and Pan MPS Syrup all carried active schemes — flagged each one, she was glad to hear about the deals. Volini Gel pack size confirmed as 100gm this time.",
        commitment: "Order is growing week over week",
      },
    ],
    order_history: [
      { sku_code: "J0042294", name: "CROCIN 650 TABLET", pack_size: "1*15", qty: 20, when: "Day 1" },
      { sku_code: "J0010291", name: "DOLO-650 TABLET", pack_size: "15'S", qty: 30, when: "Day 1" },
      { sku_code: "J0034539", name: "VOLINI GEL", pack_size: "75GM", qty: 15, when: "Day 1" },
      { sku_code: "J0006463", name: "CANDID CREAM", pack_size: "50GM", qty: 10, when: "Day 1" },
      { sku_code: "J0018841", name: "LIV 52 SYRUP", pack_size: "200ML", qty: 10, when: "Day 1" },
      { sku_code: "PROD1750", name: "4PCOS TABLET", pack_size: "10'S", qty: 12, when: "Day 2" },
      { sku_code: "PROD4392", name: "VOLINI MAXX SPRAY", pack_size: "55 GM", qty: 10, when: "Day 2" },
      { sku_code: "J0050820", name: "PAN MPS SYRUP", pack_size: "200ML", qty: 6, when: "Day 2" },
    ],
    usual_items: [],
    objective:
      "MOMENTUM CALL — the order is bigger this week, more lines than the first two calls, and Priya sounds noticeably more confident on the phone now. Take Crocin 650, Dolo 650, and Volini Gel 75gm as clean matches. At some point she'll ask for \"Coldact\" — this is NOT in the catalog; resolve it as not_found and point her at the manual search bar rather than guessing a substitute. She may also try the manual search bar herself this time (e.g. typing \"cetaphil lotion\") — when a `catalog_search` message arrives, that's her doing it, not a tool call from you; just acknowledge the add if it lands via state_sync. Close with Shelcal-500 as one more addition, then confirm once the cart is fully green.",
    nudge: "Aaj ka order thoda bada hai, Priya ji — join whenever ready.",
  },
];

export function scenariosFor(pharmacyId: string): Scenario[] {
  return SCENARIOS.filter((s) => s.pharmacy_id === pharmacyId);
}

export function scenarioById(id: string): Scenario | undefined {
  return SCENARIOS.find((s) => s.id === id);
}

// ── Brain payload (PHARMACY CONTEXT) ────────────────────────────────────────

/** Folds pharmacy + scenario into the session payload the brain consumes (DESIGN.md §4). */
export function buildBrainPayload(scenario: Scenario): Record<string, unknown> {
  const p = pharmacyById(scenario.pharmacy_id);
  return {
    language: "Hindi",
    scenario: {
      call_type: scenario.call_type,
      joined_from_nudge: scenario.nudge,
      pharmacy: {
        name: p.name,
        owner: p.owner,
        city: p.city,
        area: p.area,
        since: p.since,
        volume: p.volume_line,
        credit: p.credit_line,
        tags: p.tags,
      },
      prior_calls: scenario.prior_calls,
      order_history: scenario.order_history,
      usual_items: scenario.usual_items,
      todays_call_objective: scenario.objective,
    },
  };
}
