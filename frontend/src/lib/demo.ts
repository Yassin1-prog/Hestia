/**
 * Fallback data so the UI stays demoable when the FastAPI backend is offline or misconfigured.
 * E-mail addresses (example.com) and listing links are placeholders, not real landlords.
 * Approving a demo listing never sends an e-mail.
 */
import type { Property, SearchResult, SearchStats } from "./types";

interface DemoSet {
  match: RegExp;
  stats: SearchStats;
  reply: string;
  properties: Property[];
}

const PANGRATI: DemoSet = {
  match: /.*/,
  stats: { scanned: 35, rejected: 32, rejectReason: "poor natural light or no pets allowed" },
  reply:
    "I scanned 35 rental listings across Pangrati and Mets and rejected 32: most were dark " +
    "ground-floor units or explicitly refused dogs. The three below are bright, under €650 and " +
    "open to a labrador. My top pick is the third-floor two-bedroom on Archimidous Street: the " +
    "second bedroom works as a quiet home office and the balcony faces the National Garden side. " +
    "The listings leave a few things unanswered, such as the pet deposit and whether building " +
    "fees are included. Approve a viewing and I will put those questions to the landlord.",
  properties: [
    {
      url: "https://www.spitogatos.gr/enoikiaseis-katoikies/pagkrati?demo=1",
      title: "Two-bedroom with balcony",
      location: "Pangrati, Archimidous St.",
      price: 640,
      sqm: 78,
      floor: "3rd",
      features: ["South-facing balcony", "Pets allowed", "Second bedroom", "Natural gas heating"],
      agent_name: "Eleni Markou",
      agent_phone: null,
      agent_email: "eleni.markou@example.com",
      missing_info: [
        "Is there a pet deposit for a large dog?",
        "Are building fees included in the rent?",
      ],
      agentic_score: 9.5,
      score_reason:
        "Third-floor corner unit with a deep balcony for your labrador, a spare bedroom for the " +
        "home office and a 6-minute walk to the Evangelismos metro.",
      scam_verdict: "SAFE",
    },
    {
      url: "https://www.spitogatos.gr/enoikiaseis-katoikies/mets?demo=2",
      title: "Renovated flat near the Panathenaic Stadium",
      location: "Mets, Markou Mousourou St.",
      price: 610,
      sqm: 64,
      floor: "4th",
      features: ["Renovated 2023", "Large windows", "Pets negotiable", "Elevator"],
      agent_name: "Nikos Vlachos",
      agent_phone: null,
      agent_email: "nikos.vlachos@example.com",
      missing_info: [
        "Would the owner accept a labrador?",
        "Is the living room large enough for a desk?",
      ],
      agentic_score: 8.8,
      score_reason:
        "Floor-to-ceiling windows make it the brightest option, and the open-plan living room " +
        "fits a desk setup. Pets are negotiable rather than confirmed.",
      scam_verdict: "SAFE",
    },
    {
      url: "https://www.spitogatos.gr/enoikiaseis-katoikies/pagkrati?demo=3",
      title: "Top-floor studio loft",
      location: "Pangrati, Varnava Square",
      price: 590,
      sqm: 55,
      floor: "5th",
      features: ["Rooftop terrace", "Pets allowed", "Mezzanine office nook", "A/C"],
      agent_name: "Varnava Homes",
      agent_phone: null,
      agent_email: "varnava.homes@example.com",
      missing_info: ["Is the terrace private or shared?", "When is it available from?"],
      agentic_score: 8.1,
      score_reason:
        "Shared rooftop terrace is ideal for a dog and the mezzanine doubles as an office, but " +
        "55 m² is tight for two rooms of use.",
      scam_verdict: "SAFE",
    },
  ],
};

const PENTHOUSE: DemoSet = {
  match: /penthouse|kolonaki|central athens|terrace|syntagma|plaka/i,
  stats: { scanned: 41, rejected: 38, rejectReason: "no pets allowed or no private terrace" },
  reply:
    "I scanned 41 top-floor listings in central Athens and rejected 38: most were not pet-friendly " +
    "or only had a shared roof. The best match is the Kolonaki penthouse with a 40 m² private " +
    "terrace and written pet approval in the listing. I flagged one listing in Plaka as a possible " +
    "scam (price 45% below the area median, deposit requested by wire before viewing) and left it out.",
  properties: [
    {
      url: "https://www.spitogatos.gr/enoikiaseis-katoikies/kolonaki?demo=4",
      title: "Penthouse with Lycabettus view",
      location: "Kolonaki, Skoufa St.",
      price: 1450,
      sqm: 92,
      floor: "6th (penthouse)",
      features: ["40 m² private terrace", "Pets allowed", "Fireplace", "Parking spot"],
      agent_name: "Maria Kosta",
      agent_phone: null,
      agent_email: "maria.kosta@example.com",
      missing_info: ["Is the parking spot included in the rent?", "Minimum lease term?"],
      agentic_score: 9.3,
      score_reason:
        "Private wraparound terrace with Lycabettus views, explicit pet approval and a 3-minute " +
        "walk to Evangelismos metro.",
      scam_verdict: "SAFE",
    },
    {
      url: "https://www.spitogatos.gr/enoikiaseis-katoikies/koukaki?demo=5",
      title: "Acropolis-view top floor",
      location: "Koukaki, Drakou St.",
      price: 1200,
      sqm: 74,
      floor: "5th",
      features: ["Acropolis view", "Terrace", "Pets negotiable", "Fully furnished"],
      agent_name: "Acropolis Living",
      agent_phone: null,
      agent_email: "acropolis.living@example.com",
      missing_info: ["Would the owner accept a medium-sized dog?"],
      agentic_score: 8.6,
      score_reason:
        "Unbeatable view and a quiet pedestrian street, but the pet policy still needs confirmation.",
      scam_verdict: "SAFE",
    },
    {
      url: "https://www.spitogatos.gr/enoikiaseis-katoikies/exarcheia?demo=6",
      title: "Loft penthouse near Strefi Hill",
      location: "Exarcheia, Kallidromiou St.",
      price: 980,
      sqm: 68,
      floor: "5th",
      features: ["Terrace", "Pets allowed", "High ceilings", "Near Strefi Hill park"],
      agent_name: "Kostas Dimou",
      agent_phone: null,
      agent_email: "kostas.dimou@example.com",
      missing_info: ["Is there an elevator?", "Are building fees included?"],
      agentic_score: 7.9,
      score_reason:
        "Best value per square meter with a dog park two blocks away; the neighborhood is livelier " +
        "than you might want at night.",
      scam_verdict: "SAFE",
    },
  ],
};

const STUDENT: DemoSet = {
  match: /student|ntua|campus|zografou|university|studio|€?4\d\d\b/i,
  stats: { scanned: 52, rejected: 49, rejectReason: "over budget or over 25 min from campus" },
  reply:
    "I scanned 52 listings around the NTUA Zografou campus and rejected 49 for being over a student " +
    "budget or more than 25 minutes away. I also quarantined two listings that asked for a deposit " +
    "before any viewing, a common rental scam pattern. The three below are walkable or one bus ride " +
    "from campus, and the top pick includes utilities in the rent.",
  properties: [
    {
      url: "https://www.spitogatos.gr/enoikiaseis-katoikies/zografou?demo=7",
      title: "Furnished studio by the campus gate",
      location: "Zografou, Ilision",
      price: 420,
      sqm: 32,
      floor: "2nd",
      features: ["Utilities included", "Furnished", "Fiber internet", "Desk and bookshelf"],
      agent_name: "Giorgos Papas",
      agent_phone: null,
      agent_email: "giorgos.papas@example.com",
      missing_info: ["Can the lease follow the academic year?", "Is a guarantor required?"],
      agentic_score: 9.1,
      score_reason:
        "8-minute walk to the NTUA gate with utilities and fiber included, so the real monthly " +
        "cost is the lowest of all options.",
      scam_verdict: "SAFE",
    },
    {
      url: "https://www.spitogatos.gr/enoikiaseis-katoikies/goudi?demo=8",
      title: "One-bedroom near Goudi park",
      location: "Goudi, Papadiamantopoulou St.",
      price: 470,
      sqm: 45,
      floor: "1st",
      features: ["Separate bedroom", "Balcony", "Bus 230 to campus", "Natural gas"],
      agent_name: "Goudi Rentals",
      agent_phone: null,
      agent_email: "goudi.rentals@example.com",
      missing_info: ["Are utilities included?", "Is it furnished?"],
      agentic_score: 8.4,
      score_reason:
        "A real separate bedroom for the price of a studio, 12 minutes to campus on the 230 bus.",
      scam_verdict: "SAFE",
    },
    {
      url: "https://www.spitogatos.gr/enoikiaseis-katoikies/ano-ilisia?demo=9",
      title: "Shared-flat room with study space",
      location: "Ano Ilisia, Kouponia",
      price: 330,
      sqm: 18,
      floor: "3rd",
      features: ["Room in 3-bed flat", "All bills included", "Students only", "Quiet building"],
      agent_name: "Dimitra Lazou",
      agent_phone: null,
      agent_email: "dimitra.lazou@example.com",
      missing_info: ["Who are the current flatmates?", "Is cleaning shared or included?"],
      agentic_score: 7.6,
      score_reason:
        "Cheapest safe option and a 15-minute walk to campus, at the cost of sharing a kitchen.",
      scam_verdict: "SAFE",
    },
  ],
};

type Insights = Required<Pick<Property, "pros" | "cons" | "metrics">>;

const m = (name: string, score: number, note: string) => ({ name, score, note });

/** What the listing agent concluded for each demo listing (keyed by its `?demo=` id). */
const INSIGHTS: Record<string, Insights> = {
  "1": {
    pros: [
      "Balcony and explicit pet approval",
      "Spare bedroom for a home office",
      "6-minute walk to Evangelismos metro",
    ],
    cons: ["Pet deposit not stated", "Building fees may be extra"],
    metrics: [
      m("Price & value", 8, "€8.2/m², below the Pangrati median"),
      m("Space & layout", 9, "Two bedrooms, 78 m², corner unit"),
      m("Location", 9, "Quiet street, metro and park nearby"),
      m("Condition & light", 9, "Third floor, south-facing balcony"),
      m("Your must-haves", 10, "Bright, pets allowed, under budget"),
    ],
  },
  "2": {
    pros: [
      "Brightest option, floor-to-ceiling windows",
      "Renovated in 2023",
      "Elevator in the building",
    ],
    cons: ["Pets only negotiable, not confirmed", "One bedroom: desk shares the living room"],
    metrics: [
      m("Price & value", 8, "€9.5/m², fair for a renovation"),
      m("Space & layout", 7, "64 m², open-plan living room"),
      m("Location", 9, "Next to the Panathenaic Stadium"),
      m("Condition & light", 10, "Renovated, large windows, 4th floor"),
      m("Your must-haves", 7, "Pet policy still to confirm"),
    ],
  },
  "3": {
    pros: ["Rooftop terrace for the dog", "Mezzanine works as an office", "Cheapest of the three"],
    cons: ["55 m² is tight", "Terrace may be shared"],
    metrics: [
      m("Price & value", 9, "€590, lowest rent on the shortlist"),
      m("Space & layout", 6, "55 m² loft with a mezzanine"),
      m("Location", 8, "On Varnava Square, lively but central"),
      m("Condition & light", 8, "Top floor, light from the terrace"),
      m("Your must-haves", 8, "Pets allowed, bright, office nook"),
    ],
  },
  "4": {
    pros: [
      "40 m² private terrace",
      "Pet approval written in the listing",
      "Parking spot available",
    ],
    cons: ["Most expensive option", "Parking may cost extra"],
    metrics: [
      m("Price & value", 6, "€15.8/m², premium Kolonaki pricing"),
      m("Space & layout", 9, "92 m² penthouse with fireplace"),
      m("Location", 10, "3 minutes to Evangelismos metro"),
      m("Condition & light", 9, "Penthouse, Lycabettus views"),
      m("Your must-haves", 10, "Private terrace and pets allowed"),
    ],
  },
  "5": {
    pros: ["Acropolis view from the terrace", "Quiet pedestrian street", "Fully furnished"],
    cons: ["Pet policy unconfirmed", "Furnished: less room for your own things"],
    metrics: [
      m("Price & value", 7, "€16.2/m², the view carries a premium"),
      m("Space & layout", 7, "74 m² top floor"),
      m("Location", 9, "Koukaki, walk to the Acropolis"),
      m("Condition & light", 9, "Top floor with open views"),
      m("Your must-haves", 7, "Terrace yes, pets to confirm"),
    ],
  },
  "6": {
    pros: ["Best value per m²", "Dog park two blocks away", "High ceilings"],
    cons: ["Livelier neighborhood at night", "Elevator not mentioned"],
    metrics: [
      m("Price & value", 9, "€14.4/m², cheapest of the penthouses"),
      m("Space & layout", 7, "68 m² loft with terrace"),
      m("Location", 7, "Near Strefi Hill, noisy evenings"),
      m("Condition & light", 8, "5th floor, high ceilings"),
      m("Your must-haves", 8, "Terrace and pets allowed"),
    ],
  },
  "7": {
    pros: [
      "Utilities and fiber included",
      "8-minute walk to the NTUA gate",
      "Furnished with a desk",
    ],
    cons: ["32 m² studio", "Lease term may not follow the academic year"],
    metrics: [
      m("Price & value", 10, "Lowest real monthly cost, bills included"),
      m("Space & layout", 6, "32 m² studio"),
      m("Location", 10, "Walkable to campus"),
      m("Condition & light", 7, "2nd floor, furnished"),
      m("Your must-haves", 9, "Student budget, near campus"),
    ],
  },
  "8": {
    pros: ["Separate bedroom for a studio price", "Balcony", "One bus to campus"],
    cons: ["Utilities probably extra", "Furniture not stated"],
    metrics: [
      m("Price & value", 8, "€10.4/m² for a one-bedroom"),
      m("Space & layout", 8, "45 m² with a real bedroom"),
      m("Location", 7, "12 minutes to campus on the 230"),
      m("Condition & light", 7, "1st floor with balcony"),
      m("Your must-haves", 8, "Under budget, near campus"),
    ],
  },
  "9": {
    pros: ["Cheapest safe option", "All bills included", "Quiet, students-only building"],
    cons: ["Shared kitchen and bathroom", "18 m² room"],
    metrics: [
      m("Price & value", 9, "€330 with every bill included"),
      m("Space & layout", 5, "18 m² room in a shared flat"),
      m("Location", 7, "15-minute walk to campus"),
      m("Condition & light", 7, "3rd floor, quiet building"),
      m("Your must-haves", 7, "Budget fits, privacy is limited"),
    ],
  },
};

/** Interior photos from Unsplash (free license), bundled in public/demo so the demo works offline. */
const PHOTOS: Record<string, number[]> = {
  "1": [0, 22, 4],
  "2": [3, 9, 26],
  "3": [20, 16, 10],
  "4": [2, 25, 21],
  "5": [13, 17, 5],
  "6": [23, 12, 27],
  "7": [14, 10, 1],
  "8": [5, 15, 4],
  "9": [26, 21, 3],
};

const photo = (n: number) => `/demo/photo-${String(n).padStart(2, "0")}.jpg`;

function withInsights(p: Property): Property {
  const id = /[?&]demo=(\d+)/.exec(p.url)?.[1];
  if (!id) return p;
  return { ...p, ...INSIGHTS[id], images: (PHOTOS[id] ?? []).map(photo) };
}

const DEMO_SETS = [PENTHOUSE, STUDENT, PANGRATI];

export function demoResult(query: string, notice: string): SearchResult {
  const set = DEMO_SETS.find((s) => s.match.test(query)) ?? PANGRATI;
  return {
    query,
    reply: set.reply,
    properties: set.properties.map(withInsights),
    stats: set.stats,
    source: "demo",
    notice,
  };
}
