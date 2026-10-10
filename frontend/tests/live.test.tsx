// @vitest-environment jsdom
// Renders EVERY page against REAL API responses recorded from a running backend (member4/scripts/record_fixtures.py).
// Catches runtime crashes / shape mismatches between backend and UI. Not a visual check.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EventProvider } from "../src/hooks/useEvent";
import { NotifyProvider } from "../src/hooks/useNotify";
import AppLayout from "../src/layouts/AppLayout";
import Dashboard from "../src/pages/Dashboard";
import Campaigns from "../src/pages/Campaigns";
import CampaignDetail from "../src/pages/CampaignDetail";
import ParticipantsPage from "../src/pages/Participants";
import FollowUpQueue from "../src/pages/FollowUpQueue";
import EventsPage from "../src/pages/EventsPage";
import AnalyticsPage from "../src/pages/AnalyticsPage";
import SettingsPage from "../src/pages/SettingsPage";
import NewCampaign from "../src/pages/NewCampaign";
import LeadsPage from "../src/pages/LeadsPage";
import JoinPage from "../src/pages/JoinPage";
import settings from "./fixtures/settings.json";
import exotel from "./fixtures/exotel.json";
import events from "./fixtures/events.json";
import campaigns from "./fixtures/campaigns.json";
import campaign from "./fixtures/campaign.json";
import recipients from "./fixtures/recipients.json";
import attempts from "./fixtures/attempts.json";
import intents from "./fixtures/intents.json";
import followups from "./fixtures/followups.json";
import queue from "./fixtures/queue.json";
import participants from "./fixtures/participants.json";
import history from "./fixtures/history.json";
import analytics from "./fixtures/analytics.json";
import analyticsCampaign from "./fixtures/analytics_campaign.json";
import meta from "./fixtures/meta.json";
import overview from "./fixtures/overview.json";
import leads from "./fixtures/leads.json";
import leadSummary from "./fixtures/lead_summary.json";
import voice from "./fixtures/voice.json";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const cid = meta.campaign_id;
function route(url: string): unknown {
  const [path, qs = ""] = url.split("?");
  const q = new URLSearchParams(qs);
  const table: Record<string, unknown> = {
    "/api/settings": settings, "/api/settings/exotel-readiness": exotel, "/api/events": events,
    "/api/campaigns": campaigns, [`/api/campaigns/${cid}`]: campaign, [`/api/campaigns/${cid}/recipients`]: recipients,
    [`/api/campaigns/${cid}/attempts`]: attempts, [`/api/campaigns/${cid}/intents`]: intents,
    "/api/followups": followups, "/api/followups/queue": queue, "/api/recipients": participants,
    [`/api/recipients/${meta.history_recipient_id}/history`]: history,
    "/api/analytics": q.get("campaign_id") ? analyticsCampaign : analytics,
    "/api/campaigns/overview": overview, "/api/voice/status": voice,
    [`/api/campaigns/${participants[0].campaign_id}/recipients/${participants[0].id}/browser-call`]:
      { attempt_id: 7, status: "answered", mode: "main", language: "en", message: "Hello from the event team.", simulated: true, participant: participants[0].name },
    "/api/browser-calls/7/hangup": { attempt_id: 7, status: "completed", simulated: true },
    [`/api/events/${meta.event_id}`]: events.find((e) => e.id === meta.event_id),
    [`/api/events/${meta.event_id}/leads`]: leads, [`/api/events/${meta.event_id}/leads/summary`]: leadSummary,
  };
  if (!(path in table)) throw new Error(`unmocked endpoint ${path}`);
  return table[path];
}

let root: Root; let host: HTMLElement; let errors: string[]; let calls: string[];
beforeEach(() => {
  errors = []; calls = [];
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    calls.push(url);
    try { return new Response(JSON.stringify(route(url)), { status: 200 }); }
    catch (e) { errors.push((e as Error).message); return new Response("{}", { status: 404 }); }
  }));
  vi.spyOn(console, "error").mockImplementation((...a: unknown[]) => {
    const s = String(a[0]);
    if (!s.includes("not wrapped in act") && !s.includes("act(")) errors.push(s.slice(0, 300));
  });
  try { localStorage.clear(); } catch { /* ignore */ }
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function mount(path: string) {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[path]}><NotifyProvider><EventProvider>
        <Routes><Route element={<AppLayout />}>
          <Route index element={<Dashboard />} /><Route path="campaigns" element={<Campaigns />} />
          <Route path="campaigns/new" element={<NewCampaign />} /><Route path="campaigns/:id" element={<CampaignDetail />} />
          <Route path="participants" element={<ParticipantsPage />} /><Route path="followups" element={<FollowUpQueue />} />
          <Route path="events" element={<EventsPage />} /><Route path="analytics" element={<AnalyticsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="leads" element={<LeadsPage />} />
        </Route><Route path="join/:eventId" element={<JoinPage />} /></Routes>
      </EventProvider></NotifyProvider></MemoryRouter>);
  });
  for (let i = 0; i < 4; i++) await act(async () => { await new Promise((r) => setTimeout(r, 25)); });
}
const text = () => host.textContent ?? "";
function healthy() {
  expect(errors).toEqual([]);
  expect(text()).not.toContain("Something went wrong");
  expect(text()).toContain("Cadence");
}

describe("every page renders against real recorded API data", () => {
  it("dashboard", async () => {
    await mount("/");
    healthy();
    for (const s of [meta.event_name, "Expected attending", "Needs attention", "Campaigns", "reached", "fictional participants, simulated calls"]) expect(text()).toContain(s);
  });
  it("campaigns list (management view: progress, next step, view and delete)", async () => {
    await mount("/campaigns");
    healthy();
    for (const s of [meta.campaign_name, "Progress", "Next step", "Need follow-up", "View", "Delete"]) expect(text()).toContain(s);
  });
  it("leads (pipeline, sources, readiness)", async () => {
    await mount("/leads");
    healthy();
    for (const s of ["Ready to convert", "Pipeline", "Where leads come from", "Registration form", "Copy sign-up link", "Sample Lead"]) expect(text()).toContain(s);
    const why = [...host.querySelectorAll("button")].find((b) => /^Why \d+/.test(b.textContent ?? ""))!;
    await act(async () => { why.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(text()).toContain("How this readiness score is made");
    expect(text()).toContain("does not predict");
    expect(errors).toEqual([]);
  });
  it("public sign-up page needs explicit consent and posts a registration-form lead", async () => {
    await mount(`/join/${meta.event_id}`);
    expect(errors).toEqual([]);
    expect(text()).toContain(meta.event_name);
    expect(text()).toContain("may phone me about this event");
    expect(text()).not.toContain("Dashboard");          // public page: no organiser navigation
    const btn = [...host.querySelectorAll("button")].find((b) => b.textContent === "Sign up") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);                      // disabled until the consent box is ticked
  });
  it("campaign detail (attempts, intents, follow-ups, clarification)", async () => {
    await mount(`/campaigns/${cid}`);
    healthy();
    for (const s of ["Recipients", "Call attempts & classified responses", "Follow-ups", "Clarification", "Sample Participant 0"]) expect(text()).toContain(s);
  });
  it("participants + history expands", async () => {
    await mount("/participants");
    healthy();
    expect(text()).toContain("Sample Participant 0");
    const btn = [...host.querySelectorAll("button")].find((b) => b.textContent === "History")!;
    await act(async () => { btn.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
    expect(errors).toEqual([]);
    expect(text()).toContain("Calls");
  });
  it("participants: browser demo call opens, says it is not a phone call, and hangs up cleanly", async () => {
    await mount("/participants");
    healthy();
    const open = [...host.querySelectorAll("button")].find((b) => /Manual call/.test(b.textContent ?? ""))!;
    await act(async () => { open.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
    expect(errors).toEqual([]);
    for (const s of ["Browser demo, not a phone call", "Hello from the event team.", "Say it", "Voice is off"]) expect(text()).toContain(s);
    const hang = [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Hang up"))!;
    await act(async () => { hang.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
    expect(calls.some((u) => u.endsWith("/browser-calls/7/hangup"))).toBe(true);
    expect(text()).not.toContain("Say it");
  });
  it("participants: live call dialog opens, is labelled a demo, and cannot start without a voice key", async () => {
    await mount("/participants");
    healthy();
    const open = [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Live call"))!;
    await act(async () => { open.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
    expect(errors).toEqual([]);
    for (const s of ["Browser demo, not a phone call", "Ready", "Voice is off"]) expect(text()).toContain(s);
    const start = [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Start live call")) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
    expect(calls.some((u) => u.includes("browser-call"))).toBe(false);     // nothing is started until the person presses start
  });
  it("follow-up queue", async () => { await mount("/followups"); healthy(); expect(text()).toContain("Next:"); });
  it("events", async () => {
    await mount("/events");
    healthy();
    for (const s of ["Sample", "Venue", "Campus Code Sprint", "Hack Night Workshop", "not configured"]) expect(text()).toContain(s);
  });
  it("analytics", async () => { await mount("/analytics"); healthy(); for (const t of ["Responses", "Expected attending", "Accepted RSVP", "By language", "How the figures are calculated"]) expect(text()).toContain(t); });
  it("settings (incl. exotel readiness + sample buttons)", async () => {
    await mount("/settings");
    healthy();
    for (const s of ["Exotel readiness", "Voice (ElevenLabs)", "Key not set", "Not ready", "Load sample events and run simulation", "Remove all sample data"]) expect(text()).toContain(s);
    expect(text()).not.toContain("SUPER");
  });
  it("new campaign wizard", async () => { await mount("/campaigns/new"); healthy(); expect(text()).toContain("Campaign name"); expect(calls.length).toBeGreaterThan(0); });
});
