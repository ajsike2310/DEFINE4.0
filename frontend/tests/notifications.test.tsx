// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NotifyProvider, useNotify } from "../src/hooks/useNotify";
import { useQueueWatcher } from "../src/hooks/useQueueWatcher";
import { ConfirmDialog, NotificationBell, ToastViewport, relativeTime } from "../src/components/Notifications";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root; let host: HTMLElement;
let api: ReturnType<typeof useNotify>;

function Probe() { api = useNotify(); return null; }
function Where() { return <span data-testid="loc">{useLocation().pathname}</span>; }

beforeEach(() => {
  try { localStorage.clear(); } catch { /* ignore */ }
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.useRealTimers(); vi.unstubAllGlobals(); });

async function mount(extra?: React.ReactNode) {
  await act(async () => {
    root.render(<MemoryRouter><NotifyProvider><Probe /><NotificationBell /><ToastViewport /><ConfirmDialog /><Where />{extra}</NotifyProvider></MemoryRouter>);
  });
}
const text = () => host.textContent ?? "";
const wait = (ms: number) => act(async () => { await new Promise((r) => setTimeout(r, ms)); });
const q = <T extends Element>(s: string) => host.querySelector<T>(s);
const click = (el: Element | null) => act(async () => { el?.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
const byText = (sel: string, t: string) => [...host.querySelectorAll(sel)].find((e) => e.textContent?.includes(t)) ?? null;

describe("toasts", () => {
  it("shows title and message; errors are announced as alerts, others as status", async () => {
    await mount();
    await act(async () => { api.success("Campaign started", "11 calls placed."); api.error("That did not work", "Backend unreachable."); });
    expect(text()).toContain("Campaign started");
    expect(text()).toContain("11 calls placed.");
    expect(q('[role="alert"]')?.textContent).toContain("That did not work");
    expect(q('[role="status"]')?.textContent).toContain("Campaign started");
  });

  it("dismisses on the close button and by itself after its duration", async () => {
    await mount();
    await act(async () => { api.notify({ title: "Closable", duration: 0 }); api.notify({ title: "Short lived", duration: 60 }); });
    expect(text()).toContain("Short lived");
    await wait(450);
    expect(text()).not.toContain("Short lived");          // auto-dismissed
    expect(text()).toContain("Closable");                 // duration 0 = sticky
    await click(q('button[aria-label="Dismiss notification"]'));
    await wait(350);
    expect(host.querySelector('section[aria-label="Notifications"]')?.textContent).not.toContain("Closable");
  });

  it("ignores an identical notification fired twice at once", async () => {
    await mount();
    await act(async () => { api.info("Same thing", "twice"); api.info("Same thing", "twice"); });
    expect(host.querySelectorAll('section[aria-label="Notifications"] [role="status"]').length).toBe(1);
  });

  it("keeps at most four toasts on screen", async () => {
    await mount();
    await act(async () => { for (let i = 0; i < 7; i++) api.notify({ title: `n${i}`, duration: 0 }); });
    expect(host.querySelectorAll('section[aria-label="Notifications"] [role="status"]').length).toBe(4);
  });

  it("an action button navigates and closes the toast", async () => {
    await mount();
    await act(async () => { api.notify({ title: "New follow-up", action: { label: "Open queue", to: "/followups" }, duration: 0 }); });
    await click(byText("button", "Open queue"));
    expect(q('[data-testid="loc"]')?.textContent).toBe("/followups");
  });
});

describe("notification centre (bell)", () => {
  it("counts unread, lists history, marks read and clears", async () => {
    await mount();
    expect(q("button[aria-haspopup]")?.getAttribute("aria-label")).toBe("Notifications");
    await act(async () => { api.success("One"); api.warn("Two", "careful"); });
    expect(q("button[aria-haspopup]")?.getAttribute("aria-label")).toBe("Notifications, 2 unread");
    await click(q("button[aria-haspopup]"));
    const panel = q('[role="dialog"]')!;
    expect(panel.textContent).toContain("Two");
    expect(panel.textContent).toContain("careful");
    await click(byText("button", "Mark all read"));
    expect(q("button[aria-haspopup]")?.getAttribute("aria-label")).toBe("Notifications");
    await click(byText("button", "Clear"));
    expect(q('[role="dialog"]')?.textContent).toContain("Nothing yet");
  });

  it("closes on Escape and marks everything read", async () => {
    await mount();
    await act(async () => { api.info("Unread one"); });
    await click(q("button[aria-haspopup]"));
    await act(async () => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })); });
    expect(q('[role="dialog"]')).toBeNull();
    expect(q("button[aria-haspopup]")?.getAttribute("aria-label")).toBe("Notifications");
  });

  it("history survives a reload; preview toasts with keep:false are not stored", async () => {
    await mount();
    await act(async () => { api.success("Kept"); api.notify({ title: "Preview only", keep: false }); });
    act(() => root.unmount());
    root = createRoot(host);
    await mount();
    await click(q("button[aria-haspopup]"));
    expect(q('[role="dialog"]')?.textContent).toContain("Kept");
    expect(q('[role="dialog"]')?.textContent).not.toContain("Preview only");
  });

  it("formats relative times", () => {
    const now = 1_000_000_000_000;
    expect(relativeTime(now - 10_000, now)).toBe("just now");
    expect(relativeTime(now - 5 * 60_000, now)).toBe("5 min ago");
    expect(relativeTime(now - 3 * 3_600_000, now)).toBe("3 h ago");
  });
});

describe("confirm dialog (replaces window.confirm)", () => {
  it("resolves true on confirm, false on cancel and on Escape; danger focuses Cancel", async () => {
    await mount();
    let result: boolean | null = null;
    await act(async () => { void api.confirm({ title: "Cancel this campaign?", message: "No further calls.", confirmLabel: "Cancel campaign", cancelLabel: "Keep it", danger: true }).then((r) => (result = r)); });
    expect(q('[role="alertdialog"]')?.textContent).toContain("Cancel this campaign?");
    expect(document.activeElement?.textContent).toBe("Keep it");
    await click(byText("button", "Cancel campaign"));
    expect(result).toBe(true);
    expect(q('[role="alertdialog"]')).toBeNull();

    await act(async () => { void api.confirm({ title: "Sure?" }).then((r) => (result = r)); });
    await click(byText("button", "Cancel"));
    expect(result).toBe(false);

    await act(async () => { void api.confirm({ title: "Again?" }).then((r) => (result = r)); });
    await act(async () => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })); });
    expect(result).toBe(false);
    expect(q('[role="alertdialog"]')).toBeNull();
  });
});

describe("live follow-up alerts", () => {
  function Watch({ id }: { id: number }) { useQueueWatcher(id); return null; }
  const item = (id: number, name: string) => ({ followup_id: id, participant_name: name, reason: "unclear", priority: 2, recommended_action: "Ask one clarifying question." });
  function stubQueue(...responses: unknown[][]) {
    let i = 0;
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(responses[Math.min(i++, responses.length - 1)]), { status: 200 })));
  }

  it("announces only items that are new after the first (baseline) poll", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    stubQueue([item(1, "Asha")], [item(1, "Asha"), item(2, "Ben")], [item(1, "Asha"), item(2, "Ben"), item(3, "Cy"), item(4, "Di")]);
    await mount(<Watch id={1} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(text()).not.toContain("New follow-up");                       // baseline: Asha is old news
    await act(async () => { await vi.advanceTimersByTimeAsync(15_100); });
    expect(text()).toContain("New follow-up: Ben");
    expect(text()).not.toContain("Asha");
    await act(async () => { await vi.advanceTimersByTimeAsync(15_100); });
    expect(text()).toContain("2 new follow-ups need attention");
  });

  it("stays silent when the organiser turned alerts off, and survives a failing backend", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    localStorage.setItem("cadence.alerts.followups", "off");
    stubQueue([item(1, "Asha")], [item(1, "Asha"), item(2, "Ben")]);
    await mount(<Watch id={1} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(15_100); });
    expect(text()).not.toContain("New follow-up");
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("down"); }));
    await act(async () => { await vi.advanceTimersByTimeAsync(15_100); });
    expect(text()).not.toContain("went wrong");                         // quiet failure, no error toast spam
  });
});
