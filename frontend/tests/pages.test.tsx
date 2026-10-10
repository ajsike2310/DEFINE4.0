// @vitest-environment jsdom
// Render tests: real pages + real api client, mocked fetch. Not a visual check.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EventProvider } from "../src/hooks/useEvent";
import { NotifyProvider } from "../src/hooks/useNotify";
import { ToastViewport } from "../src/components/Notifications";
import Dashboard from "../src/pages/Dashboard";
import FollowUpQueue from "../src/pages/FollowUpQueue";
import NewCampaign from "../src/pages/NewCampaign";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const EVENT = { id: 1, name: "[SAMPLE] DEFINE 4.0", description: "", approved_info: { venue: "MBCET" }, organizer_contact: null, is_demo: true, campaign_count: 1 };
const totals = { campaigns: 1, recipients: 10, calls_attempted: 13, calls_finished: 13, calls_answered: 8, recipients_contacted: 10,
  recipients_responded: 8, retries: 3, failed_or_unanswered: 5, simulated_calls: 13, real_calls: 0 };
const outcomes = { confirmed: 3, acknowledged: 0, declined: 1, callback_requested: 1, information_requested: 1, unclear: 1, human_required: 0, opted_out: 1, no_response: 2, pending: 0 };
const ANALYTICS = { source: "all", totals, outcomes, followups: { pending: 3, completed: 0, cancelled: 0 }, needs_attention: 5, needs_review: 1,
  headcount: { participants: 11, confirmed: 3, declined: 1, unknown: 7, unknown_breakdown: { unclear: 2, opted_out: 1 }, floor: 3, ceiling: 10, certainty: 0.3636 },
  clarification: { attempted: 0, resolved: 0 },
  rates: { answer_rate: 0.6154, confirmation_rate: 0.375 }, by_language: [{ language: "en", recipients: 10, attempts: 13, answered: 8, ...outcomes }] };
const QUEUE = [{ followup_id: 7, campaign_id: 1, campaign_name: "Camp A", event_id: 1, recipient_id: 4, participant_name: "Sample Participant 4", participant_ref: "SAMPLE-004",
  reason: "unclear", action_type: "human_review", status: "pending", priority: 2, priority_reason: "response could not be understood safely", latest_outcome: "unclear",
  recommended_action: "Ask one clarifying yes/no question (if offered), otherwise contact the participant yourself.",
  can_clarify: true, clarification_attempted: false, scheduled_at: null, note: "hedging language", is_simulated: true, created_at: "2026-10-09T10:00:00Z" }];

const ROUTES: Record<string, unknown> = {
  "/api/settings": { provider: "demo", languages: [], retry_policy: {}, purposes: [] },
  "/api/events": [EVENT], "/api/analytics": ANALYTICS, "/api/campaigns": [], "/api/followups/queue": QUEUE,
};
let calls: string[] = [];
let root: Root; let host: HTMLElement;

beforeEach(() => {
  calls = [];
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });   // jsdom lacks it (recharts)
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    calls.push(url);
    const key = url.split("?")[0];
    return new Response(JSON.stringify(key in ROUTES ? ROUTES[key] : { error: { code: "not_found", message: "x" } }), { status: key in ROUTES ? 200 : 404 });
  }));
  try { localStorage.clear(); } catch { /* ignore */ }
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); });

async function mount(ui: React.ReactElement) {
  await act(async () => { root.render(<MemoryRouter><NotifyProvider><EventProvider>{ui}</EventProvider><ToastViewport /></NotifyProvider></MemoryRouter>); });
  await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
}
function setValue(el: HTMLInputElement | HTMLTextAreaElement, v: string) {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, v);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}
const click = (el: Element) => act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
const button = (label: string) => [...host.querySelectorAll("button")].find((b) => b.textContent?.includes(label))!;

describe("pages", () => {
  it("dashboard shows the selected event, sample label, event-scoped stats and the attention list", async () => {
    await mount(<Dashboard />);
    const t = host.textContent!;
    expect(t).toContain("[SAMPLE] DEFINE 4.0");
    expect(t).toContain("Expected attending");
    expect(t).toContain("Sample Participant 4");
    expect(t).toContain("36.4% certain");
    expect(calls.some((u) => u.startsWith("/api/analytics") && u.includes("event_id=1"))).toBe(true);
  });

  it("follow-up queue shows reason, recommended action and simulated label", async () => {
    await mount(<FollowUpQueue />);
    const t = host.textContent!;
    expect(t).toContain("P2 Needs a person");
    expect(t).toContain("Next:");
    expect(t).toContain("Simulated");
    expect(t).toContain("Mark complete");
    expect(button("Clarify call")).toBeTruthy();
  });

  it("clicking the clarify button calls the clarify endpoint for that participant", async () => {
    ROUTES["/api/recipients/4/clarify"] = { dispatched: 1, skipped: [] };
    await mount(<FollowUpQueue />);
    await click(button("Clarify call"));
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    expect(calls).toContain("/api/recipients/4/clarify");
    expect(host.textContent).toContain("Clarification call placed");
    delete ROUTES["/api/recipients/4/clarify"];
  });

  it("wizard refuses to continue while the message still has an organiser placeholder", async () => {
    await mount(<NewCampaign />);
    setValue(host.querySelector("input")!, "Deadline reminder");
    await act(async () => { host.querySelector("select")!.dispatchEvent(new Event("change", { bubbles: true })); });
    const sel = host.querySelector("select")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(sel, "submission_deadline_reminder");
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await click(button("Continue"));
    expect(host.textContent).toContain("Message — English");
    await click(button("Continue"));
    expect(host.textContent).toContain("Replace the bracketed placeholder");
    expect(host.textContent).toContain("Message — English");   // still on step 2
  });

  it("wizard disables launch until participants are added", async () => {
    await mount(<NewCampaign />);
    setValue(host.querySelector("input")!, "Attendance round 1");
    await click(button("Continue"));      // message step (attendance template has no placeholder)
    await click(button("Continue"));      // participants step
    await click(button("Continue"));      // review
    expect(host.textContent).toContain("Review" );
    expect(button("Create and launch now").disabled).toBe(true);
    expect(button("Create draft").disabled).toBe(false);
  });
});
