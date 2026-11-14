/**
 * Scripted agent runs for when the backend is offline: the same events the live agents stream
 * (backend/agent.py, backend/outreach/live.py), built from the demo data, so the UI shows the
 * agent working either way. Nothing here contacts anyone.
 */
import { formatPrice, propertyTitle, scoreLabel } from "./format";
import type { AgentEvent, LogKind, StepStatus } from "./trace";
import type { EmailOutcome, Profile, Property, SearchResult } from "./types";

type DemoEvent = AgentEvent | { type: "outcome"; outcome: EmailOutcome };

class Script {
  events: DemoEvent[] = [];
  start(step: string, title: string, detail: string) {
    this.events.push({ type: "step", step, status: "running", title, detail });
    return this;
  }
  log(step: string, text: string, kind: LogKind = "info") {
    this.events.push({ type: "log", step, text, kind });
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
  ) {
    this.events.push({ type: "agent", step, agent, label, status, detail, hub });
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

  s.start("understand", "Reading your request", "Turning your request into search filters")
    .log("understand", "Gemini is translating your request into Spitogatos filters")
    .log("understand", `Area: ${areaLabel}`);
  if (maxPrice) s.log("understand", `Max price: €${maxPrice}`);
  s.log(
    "understand",
    `Search URL ready: spitogatos.gr/enoikiaseis-katoikies/${area}${maxPrice ? `?max_price=${maxPrice}` : ""}`,
    "ok",
  ).done("understand", "Search filters ready");

  s.start("scan", "Scanning listings", "Reading every listing on the results page")
    .log("scan", "Firecrawl is opening the Spitogatos results page")
    .log("scan", `Results page downloaded (${18 + scanned} KB of text)`)
    .log("scan", "Gemini is extracting every listing card")
    .log("scan", `Found ${scanned} listings`, "ok")
    .done("scan", `Scanned ${scanned} listings`);

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
      )
      .log("inspect", `Agent ${i + 1} is opening ${shortUrl(p)}`),
  );
  props.forEach((p, i) =>
    s.agent("inspect", `listing-${i + 1}`, `Agent ${i + 1}`, "running", "Reading the full listing"),
  );
  props.forEach((p, i) =>
    s
      .log(
        "inspect",
        `Agent ${i + 1}: scored ${scoreLabel(p.agentic_score)}/10, ` +
          (p.agent_email ? `e-mail for ${p.agent_name || "the landlord"}` : "no e-mail listed") +
          `, ${plural(p.missing_info.length, "open question")}`,
        p.agent_email ? "ok" : "warn",
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
      `Listing ${i + 1}: ${risky ? "possible scam" : "safe"} (risk ${risk}%)`,
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
  s.start("brief", "Reading the listing", "Collecting what the landlord needs to know")
    .log(
      "brief",
      `Listing: ${[p.location || propertyTitle(p), p.sqm ? `${p.sqm} m²` : "", formatPrice(p.price)].filter(Boolean).join(" · ")}`,
    )
    .log("brief", `Writing on behalf of ${profile.name} <${profile.email}>`)
    .log(
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
  s.start("calendar", "Checking your calendar", "Looking for free evenings and weekend slots").log(
    "calendar",
    profile.calendarUrl?.trim()
      ? "Agent backend offline: using a sample work week instead of your calendar"
      : "No calendar connected: using a sample work week",
    "warn",
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

  s.start("send", "Sending the e-mail", "Composed for review only (dry run)")
    .log("send", `E-mail to ${p.agent_email} composed but not sent (demo listing)`, "warn")
    .done("send", "Composed, not sent (demo listing)");
  s.events.push({
    type: "outcome",
    outcome: { state: "demo", to: p.agent_email, windows: slots, ...email },
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
