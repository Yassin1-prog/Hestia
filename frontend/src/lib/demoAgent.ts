/**
 * Scripted agent runs for when the backend is offline: the same events the live agents stream
 * (backend/agent.py, backend/outreach/live.py), built from the demo data, so the UI shows the
 * agent working either way. Nothing here contacts anyone.
 */
import { SITES, siteForUrl } from "@/components/SiteLogo";

import { formatPrice, propertyTitle, scoreLabel } from "./format";
import type { AgentEvent, LogKind, StepStatus } from "./trace";
import type { EmailOutcome, Profile, Property, SearchResult } from "./types";

type DemoEvent = AgentEvent | { type: "outcome"; outcome: EmailOutcome };

class Script {
  events: DemoEvent[] = [];
  start(step: string, title: string, detail: string, sources?: string[]) {
    this.events.push({ type: "step", step, status: "running", title, detail, sources });
    return this;
  }
  log(step: string, text: string, kind: LogKind = "info", source?: string) {
    this.events.push({ type: "log", step, text, kind, source });
    return this;
  }
  done(step: string, detail: string, status: StepStatus = "done") {
    this.events.push({ type: "step", step, status, detail });
    return this;
  }
  agent(
    step: string,
    agent: string,
    label: string,
    status: StepStatus,
    detail: string,
    hub?: string,
    source?: string,
  ) {
    this.events.push({ type: "agent", step, agent, label, status, detail, hub, source });
    return this;
  }
}

function slug(property: Property): string {
  try {
    const path = new URL(property.url).pathname.split("/").filter(Boolean);
    return path[path.length - 1] || "athens";
  } catch {
    return "athens";
  }
}

function shortUrl(property: Property): string {
  try {
    const u = new URL(property.url);
    return `${u.hostname.replace(/^www\./, "")}/…/${slug(property)}`;
  } catch {
    return property.url;
  }
}

function siteOf(p: Property): string | undefined {
  return p.source ?? siteForUrl(p.url);
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export function demoSearchEvents(result: SearchResult): AgentEvent[] {
  const props = result.properties;
  const scanned = result.stats?.scanned ?? props.length;
  const rejected = result.stats?.rejected ?? Math.max(0, scanned - props.length);
  const area = props[0] ? slug(props[0]) : "athens";
  const areaLabel = area.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const maxPrice = Math.ceil(Math.max(0, ...props.map((p) => p.price ?? 0)) / 50) * 50;
  const s = new Script();

  const sites = ["spitogatos", "xe", "booking"];
  const names = "Spitogatos, xe.gr and Booking.com";
  // Rough split of the scanned listings across the three sites.
  const perSite: Record<string, number> = {
    spitogatos: Math.round(scanned * 0.45),
    xe: Math.round(scanned * 0.4),
  };
  perSite.booking = Math.max(0, scanned - perSite.spitogatos - perSite.xe);

  s.start("understand", "Reading your request", "Turning your request into search filters")
    .log("understand", `The agent is translating your request into filters for ${names}`)
    .log("understand", `Area: ${areaLabel}, Athens`);
  if (maxPrice) s.log("understand", `Max price: €${maxPrice}/month`);
  sites.forEach((k) => s.log("understand", `${SITES[k].name} search planned`, "ok", k));
  s.done("understand", "Search filters ready");

  s.start("scan", "Scanning listings", `Searching ${names} in parallel`, sites).log(
    "scan",
    "Dispatching 3 scanner agents, one per site",
  );
  sites.forEach((k) =>
    s.agent(
      "scan",
      `source-${k}`,
      SITES[k].name,
      "running",
      "Opening the results page",
      "Orchestrator",
      k,
    ),
  );
  s.log(
    "scan",
    `Spitogatos: Opening spitogatos.gr/enoikiaseis-katoikies/${area}${maxPrice ? `?max_price=${maxPrice}` : ""}`,
    "info",
    "spitogatos",
  )
    .log("scan", `xe.gr: Area ${areaLabel} is a known xe.gr area`, "info", "xe")
    .log("scan", "Booking.com: Pricing a 30-night stay, starting in two weeks", "info", "booking")
    .log(
      "scan",
      `xe.gr: Results page downloaded (${120 + scanned * 9} KB); read ${perSite.xe} listings from its data`,
      "info",
      "xe",
    )
    .log(
      "scan",
      `Spitogatos: Results page downloaded (${18 + scanned} KB); the agent is reading the listing cards`,
      "info",
      "spitogatos",
    )
    .log(
      "scan",
      "Booking.com: Results page downloaded (340 KB); the agent is reading the listing cards",
      "info",
      "booking",
    );
  sites.forEach((k) =>
    s
      .log(
        "scan",
        `${SITES[k].name}: found ${plural(perSite[k], "listing")}`,
        perSite[k] ? "ok" : "warn",
        k,
      )
      .agent(
        "scan",
        `source-${k}`,
        SITES[k].name,
        "done",
        plural(perSite[k], "listing"),
        undefined,
        k,
      ),
  );
  s.done(
    "scan",
    `Scanned ${scanned} listings (${sites.map((k) => `${perSite[k]} on ${SITES[k].name}`).join(", ")})`,
  );

  s.start(
    "rank",
    "Ranking against your request",
    "Scoring each listing against your constraints",
  ).log("rank", `Weighing price, size and description of all ${scanned} listings`);
  props.forEach((p, i) =>
    s.log(
      "rank",
      `Shortlisted #${i + 1}: ${formatPrice(p.price)}${p.sqm ? ` · ${p.sqm} m²` : ""}: ${propertyTitle(p)}`,
      "ok",
      siteOf(p),
    ),
  );
  if (rejected) {
    s.log(
      "rank",
      `Set aside ${rejected} weaker matches` +
        (result.stats?.rejectReason ? ` (${result.stats.rejectReason})` : ""),
    );
  }
  s.done("rank", `Shortlisted ${props.length} of ${scanned}`);

  s.start(
    "inspect",
    "Inspecting the shortlist",
    "Visiting the best listings for contacts and missing details",
  ).log("inspect", `Dispatching ${plural(props.length, "agent")} in parallel, one per listing`);
  props.forEach((p, i) =>
    s
      .agent(
        "inspect",
        `listing-${i + 1}`,
        `Agent ${i + 1}`,
        "running",
        `Opening ${shortUrl(p)}`,
        "Orchestrator",
        siteOf(p),
      )
      .log("inspect", `Agent ${i + 1} is opening ${shortUrl(p)}`, "info", siteOf(p)),
  );
  props.forEach((p, i) =>
    s.agent(
      "inspect",
      `listing-${i + 1}`,
      `Agent ${i + 1}`,
      "running",
      "Reading the full listing",
      undefined,
      siteOf(p),
    ),
  );
  props.forEach((p, i) =>
    s
      .log(
        "inspect",
        `Agent ${i + 1}: scored ${scoreLabel(p.agentic_score)}/10, ` +
          (p.agent_email ? `e-mail for ${p.agent_name || "the landlord"}` : "no e-mail listed") +
          `, ${plural(p.missing_info.length, "open question")}`,
        p.agent_email ? "ok" : "warn",
        siteOf(p),
      )
      .agent(
        "inspect",
        `listing-${i + 1}`,
        `Agent ${i + 1}`,
        "done",
        `${scoreLabel(p.agentic_score)}/10 · ${p.agent_email ? "e-mail found" : "no e-mail"}`,
      ),
  );
  const withEmail = props.filter((p) => p.agent_email).length;
  s.done("inspect", `Found e-mail contacts for ${withEmail} of ${props.length} listings`);

  s.start("scam", "Scam check (Oumi Iris)", "Checking the shortlist for rental-scam patterns")
    .log("scam", `Comparing price per m² against ${scanned} listings in the area`)
    .log("scam", `Sending ${plural(props.length, "listing")} to Oumi Iris`);
  props.forEach((_, i) =>
    s.agent("scam", `iris-${i + 1}`, `Listing ${i + 1}`, "running", "Under review", "Oumi Iris"),
  );
  props.forEach((p, i) => {
    const risky = p.scam_verdict === "POSSIBLY_SCAM";
    const risk = p.scam_risk_pct ?? (risky ? 72 : 4 + i * 3);
    s.log(
      "scam",
      `Listing ${i + 1}: ${risky ? "possible scam" : "safe"} (risk ${risk}%)` +
        (p.scam_reason ? `: ${p.scam_reason}` : ""),
      risky ? "warn" : "ok",
    ).agent(
      "scam",
      `iris-${i + 1}`,
      `Listing ${i + 1}`,
      risky ? "failed" : "done",
      `${risky ? "Possible scam" : "Safe"} · risk ${risk}%`,
    );
  });
  const flagged = props.filter((p) => p.scam_verdict === "POSSIBLY_SCAM").length;
  s.done("scam", flagged ? `Flagged ${plural(flagged, "possible scam")}` : "All listings passed");

  s.start("final", "Selecting the top matches", "Final scoring");
  if (props.length) {
    s.log("final", "Sorted the shortlist by match score")
      .log(
        "final",
        `Best match ${scoreLabel(props[0].agentic_score)}/10: ${props[0].score_reason}`,
        "ok",
      )
      .done(
        "final",
        `Selected the top ${props.length}, best match ${scoreLabel(props[0].agentic_score)}/10`,
      );
  } else {
    s.done("final", "No listing passed the filters", "failed");
  }
  return s.events as AgentEvent[];
}

// ---------------------------------------------------------------------------
// Outreach
// ---------------------------------------------------------------------------
const DAY = 24 * 60 * 60 * 1000;

/** Mirrors `sample_week()` + `find_free_slots()` in backend/outreach/availability.py. */
function sampleSlots(now = new Date()): { slots: string[]; conflicts: string[] } {
  const slots: string[] = [];
  const conflicts: string[] = [];
  const fmt = (d: Date) =>
    `${d.toLocaleDateString("en-GB", { weekday: "short" })} ${d.getDate()} ${d.toLocaleDateString("en-GB", { month: "short" })}`;
  for (let offset = 1; offset <= 7 && slots.length < 3; offset++) {
    const d = new Date(now.getTime() + offset * DAY);
    const label = fmt(d);
    switch (d.getDay()) {
      case 1:
        conflicts.push(`${label} evening: Gym 18:00-19:30`);
        break;
      case 3:
        conflicts.push(`${label} evening: Dinner with friends 18:30-21:00`);
        break;
      case 6:
        conflicts.push(`${label} morning: Football 10:00-12:30`);
        slots.push(`${label}, 13:00-14:00`);
        break;
      case 0:
        slots.push(`${label}, 11:00-13:00`);
        break;
      default:
        slots.push(`${label}, 18:00-20:00`);
    }
  }
  return { slots, conflicts };
}

function firstName(name: string | null): string | null {
  if (!name || /[()]/.test(name) || /homes|living|rentals|estate|agency/i.test(name)) return null;
  return name;
}

function demoEmail(p: Property, profile: Profile, windows: string[], approved?: string[]) {
  const spec = [p.sqm ? `${p.sqm} m²` : "", p.price ? `€${p.price}/month` : ""]
    .filter(Boolean)
    .join(", ");
  const greet = firstName(p.agent_name);
  const questions = approved
    ? approved
    : p.missing_info.length
      ? p.missing_info
      : ["Is the apartment still available?", "Are building fees included in the rent?"];
  const body = [
    `${greet ? `Hello ${greet},` : "Hello,"}`,
    "",
    `My name is ${profile.name} and I'm interested in your rental listing${spec ? ` (${spec})` : ""}: ${p.url}`,
    "",
    ...(questions.length
      ? ["A few questions about the property:", ...questions.map((q) => `- ${q}`), ""]
      : []),
    "I'm available for a viewing:",
    ...(windows.length ? windows : ["at a time that suits you"]).map((w) => `- ${w}`),
    "",
    "You can reach me at:",
    `- ${profile.email}`,
    "",
    "Thank you in advance,",
    profile.name,
    "",
    `Sent on behalf of ${profile.name} by their relocation assistant.`,
  ].join("\n");
  return { subject: `Viewing request: ${spec ? `${spec} apartment` : propertyTitle(p)}`, body };
}

/** Offline run of the outreach agent for a demo listing. Always a dry run. */
export function demoOutreachEvents(
  p: Property,
  profile: Profile,
  approved?: string[],
): DemoEvent[] {
  const s = new Script();
  const questions = approved ? approved.length : p.missing_info.length || 2;
  const ranker = new Set(p.missing_info.map((q) => q.trim().toLowerCase()));
  const yours = (approved ?? []).filter((q) => !ranker.has(q.trim().toLowerCase()));
  const scamLocked = p.scam_verdict === "POSSIBLY_SCAM";
  s.start("brief", "Reading the listing", "Collecting what the landlord needs to know").log(
    "brief",
    `Listing: ${[p.location || propertyTitle(p), p.sqm ? `${p.sqm} m²` : "", formatPrice(p.price)].filter(Boolean).join(" · ")}`,
  );
  if (scamLocked) {
    s.log(
      "brief",
      "Oumi Iris flagged this listing as a possible scam" +
        (p.scam_risk_pct != null ? ` (${p.scam_risk_pct}% risk)` : "") +
        ": the e-mail will be drafted but not sent",
      "warn",
    );
  }
  s.log("brief", `Writing on behalf of ${profile.name} <${profile.email}>`).log(
    "brief",
    approved && !approved.length
      ? "You cleared the questions: asking only for a viewing"
      : approved
        ? `${plural(questions, "question")} approved by you` +
          (yours.length ? `, ${yours.length} of them your own` : "")
        : `${plural(questions, "open question")} from the ranker`,
    approved ? "ok" : "info",
  );
  yours.slice(0, 3).forEach((q) => s.log("brief", `Your question: ${q}`));
  s.done("brief", "Listing and profile loaded");

  const { slots, conflicts } = sampleSlots();
  const feed = profile.calendarUrl?.trim() ?? "";
  s.start(
    "calendar",
    "Checking your calendar",
    "Looking for free evenings and weekend slots",
    feed.includes("google.com") ? ["google_calendar", "calendar"] : ["calendar"],
  ).log(
    "calendar",
    feed
      ? `Agent backend offline: using a sample work week instead of your ${feed.includes("google.com") ? "Google Calendar" : "calendar"}`
      : "No calendar connected: using a sample work week",
    "warn",
    feed.includes("google.com") ? "google_calendar" : undefined,
  );
  s.log("calendar", "Read 9 events for the next 7 days");
  conflicts.slice(0, 3).forEach((c) => s.log("calendar", `Busy ${c}`, "warn"));
  slots.forEach((w) => s.log("calendar", `Free: ${w}`, "ok"));
  s.done("calendar", `Found ${plural(slots.length, "free viewing slot")}`);

  s.start("contact", "Verifying the landlord's contact", "Checking the e-mail on the listing");
  if (!p.agent_email) {
    s.log("contact", "No usable e-mail address on the listing", "warn").done(
      "contact",
      "No e-mail address to contact",
      "failed",
    );
    s.events.push({
      type: "outcome",
      outcome: { state: "no_contact", detail: "No e-mail address on the listing.", windows: slots },
    });
    return s.events;
  }
  s.log("contact", "Demo listing: placeholder address, nothing will be sent", "warn")
    .log("contact", `Found ${p.agent_email} (from agent_email)`, "ok")
    .log("contact", "Portal and no-reply addresses filtered out")
    .log(
      "contact",
      firstName(p.agent_name)
        ? `Greeting the landlord as ${p.agent_name}`
        : "Agency listing: using a neutral greeting",
    )
    .done("contact", `Landlord reachable at ${p.agent_email}`);

  const email = demoEmail(p, profile, slots, approved);
  s.start("draft", "Writing the e-mail", "Composing the viewing request")
    .log("draft", `Proposing ${plural(slots.length, "viewing slot")} from your calendar`)
    .log(
      "draft",
      questions
        ? `Adding ${plural(questions, "question")} for the landlord`
        : "No questions: asking only for a viewing",
    )
    .log("draft", "Reply-To set to your address, so the landlord answers you directly");
  s.events.push({ type: "draft", channel: "email", to: p.agent_email, ...email });
  s.done("draft", "E-mail drafted");

  const lockDetail = scamLocked
    ? "Not sent: Oumi Iris flagged this listing as a possible scam"
    : undefined;
  s.start("send", "Sending the e-mail", "Composed for review only (dry run)")
    .log(
      "send",
      `E-mail to ${p.agent_email} composed but not sent (${scamLocked ? "Oumi Iris scam lock" : "demo listing"})`,
      "warn",
    )
    .done(
      "send",
      scamLocked ? "Composed, not sent (Oumi Iris scam lock)" : "Composed, not sent (demo listing)",
    );
  s.events.push({
    type: "outcome",
    outcome: { state: "demo", to: p.agent_email, detail: lockDetail, windows: slots, ...email },
  });
  return s.events;
}

/** A demo listing's voice call while the backend is offline (mirrors live.py's call step). */
export function demoCallEvents(p: Property, profile: Profile, approved?: string[]): DemoEvent[] {
  const s = new Script();
  const questions = approved ?? p.missing_info;
  const scamLocked = p.scam_verdict === "POSSIBLY_SCAM";
  const where = p.location || propertyTitle(p);
  s.start("brief", "Reading the listing", "Collecting what the landlord needs to know")
    .log(
      "brief",
      `Listing: ${[where, p.sqm ? `${p.sqm} m²` : "", formatPrice(p.price)].filter(Boolean).join(" · ")}`,
    )
    .log("brief", `Calling on behalf of ${profile.name}`)
    .log("brief", `${plural(questions.length, "question")} for the landlord`, "ok")
    .done("brief", "Listing and profile loaded");

  const { slots } = sampleSlots();
  s.start("calendar", "Checking your calendar", "Looking for free evenings and weekend slots", [
    "calendar",
  ]).log("calendar", "Agent backend offline: using a sample work week", "warn");
  slots.forEach((w) => s.log("calendar", `Free: ${w}`, "ok"));
  s.done("calendar", `Found ${plural(slots.length, "free viewing slot")}`);

  s.start("call", "Calling the landlord", "Preparing the voice agent (Vapi)").log(
    "call",
    "Live web call: you play the landlord through your microphone",
    "warn",
  );
  if (scamLocked) {
    const detail = "Not sent: Oumi Iris flagged this listing as a possible scam";
    s.log("call", "Oumi Iris scam lock: the call is not placed", "warn").done(
      "call",
      "Held back: Oumi Iris flagged this listing",
      "failed",
    );
    s.events.push({
      type: "outcome",
      outcome: { channel: "call", state: "dry_run", detail, windows: slots },
    });
    return s.events;
  }
  const name = profile.name || "my client";
  // Named by area and price (and size): the landlord may have several flats on offer.
  const apartment =
    `${p.sqm ? `${p.sqm} square metre ` : ""}apartment` +
    (p.location ? ` in ${p.location}` : "") +
    (p.price ? ` for ${p.price} euros a month` : "");
  const first = `Hello! I'm calling on behalf of ${name} about your ${apartment}. Is it still available?`;
  const prompt =
    `You are Domus AI, a polite, friendly real estate assistant on a phone call with the landlord ` +
    `about their ${apartment}, calling on behalf of your client, ${name}.\n\n` +
    `Goals, in order:\n1. Make sure the landlord knows which apartment you mean: always refer to ` +
    `it by its area and price (never by the price alone), then confirm it is still available.\n` +
    `2. Ask these open questions, one at a time:\n${questions.map((q) => `- ${q}`).join("\n") || "- (none: only ask for a viewing)"}\n` +
    `3. Propose one of these viewing slots: ${slots.join("; ")}.\n` +
    `4. Confirm what was agreed, thank them and say goodbye.\n\n` +
    `Keep every turn short and natural, and never invent facts about the client or the apartment.`;
  s.log("call", `Voice brief ready: ${plural(questions.length, "question")}`, "ok");
  s.events.push({
    type: "call",
    to: null,
    landlord: p.agent_name ?? null,
    system_prompt: prompt,
    first_message: first,
    questions,
    viewing_windows: slots,
  });
  s.done("call", "Voice agent on the line");
  s.events.push({
    type: "outcome",
    outcome: {
      channel: "call",
      state: "sent",
      detail: "Live voice call started in the browser",
      windows: slots,
      body: first,
    },
  });
  return s.events;
}

/** A failed run when a real listing cannot reach the backend. */
export function offlineOutreachEvents(reason: string): DemoEvent[] {
  const s = new Script();
  s.start("connect", "Starting the outreach agent", "Connecting to the agent backend")
    .log("connect", reason, "warn")
    .done("connect", "Could not reach the outreach agent: retry from Contact Requests", "failed");
  s.events.push({ type: "outcome", outcome: { state: "failed", detail: reason } });
  return s.events;
}
