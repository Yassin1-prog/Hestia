/**
 * Fallback data so the UI stays demoable when the FastAPI backend is offline or misconfigured.
 * Phone numbers and listing links are placeholders, not real landlords.
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
      agent_phone: "+30 690 000 0142",
      agent_email: null,
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
      agent_phone: "+30 690 000 0187",
      agent_email: null,
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
      agent_phone: "+30 690 000 0119",
      agent_email: null,
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
      agent_phone: "+30 690 000 0231",
      agent_email: null,
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
      agent_phone: "+30 690 000 0256",
      agent_email: null,
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
      agent_phone: "+30 690 000 0274",
      agent_email: null,
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
      agent_phone: "+30 690 000 0318",
      agent_email: null,
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
      agent_phone: "+30 690 000 0342",
      agent_email: null,
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
      agent_phone: "+30 690 000 0365",
      agent_email: null,
      missing_info: ["Who are the current flatmates?", "Is cleaning shared or included?"],
      agentic_score: 7.6,
      score_reason:
        "Cheapest safe option and a 15-minute walk to campus, at the cost of sharing a kitchen.",
      scam_verdict: "SAFE",
    },
  ],
};

const DEMO_SETS = [PENTHOUSE, STUDENT, PANGRATI];

export function demoResult(query: string, notice: string): SearchResult {
  const set = DEMO_SETS.find((s) => s.match.test(query)) ?? PANGRATI;
  return {
    query,
    reply: set.reply,
    properties: set.properties,
    stats: set.stats,
    source: "demo",
    notice,
  };
}
