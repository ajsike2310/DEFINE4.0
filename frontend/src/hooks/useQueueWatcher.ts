import { useEffect } from "react";
import { api } from "../services/api";
import { useNotify } from "./useNotify";

const POLL_MS = 15000;
const ALERTS_KEY = "cadence.alerts.followups";

/** Live follow-up alerts are on unless the organiser turned them off in Settings. */
export function getFollowupAlerts(): boolean {
  try { return localStorage.getItem(ALERTS_KEY) !== "off"; } catch { return true; }
}
export function setFollowupAlerts(on: boolean) {
  try { localStorage.setItem(ALERTS_KEY, on ? "on" : "off"); } catch { /* storage unavailable */ }
}

/** Tells the organiser when NEW follow-ups appear for the selected event (e.g. a call just finished with an
 *  unclear answer or a callback request). Derived from real queue data - nothing is invented. The first
 *  poll only records a baseline, so opening the app never announces old items. Paused while the tab is hidden. */
export function useQueueWatcher(eventId: number | undefined) {
  const { notify } = useNotify();
  useEffect(() => {
    if (!eventId) return;
    let seen: Set<number> | null = null;
    let stopped = false;
    const tick = async () => {
      if (stopped || (typeof document !== "undefined" && document.hidden)) return;
      try {
        const queue = await api.followupQueue({ eventId });
        if (stopped) return;
        const fresh = seen ? queue.filter((i) => !seen!.has(i.followup_id)) : [];
        seen = new Set(queue.map((i) => i.followup_id));        // keep the baseline current even while alerts are off
        if (!getFollowupAlerts()) return;
        if (fresh.length === 1) {
          const i = fresh[0];
          notify({ tone: i.priority === 1 ? "warn" : "info", title: `New follow-up: ${i.participant_name}`,
            message: `${i.reason}. ${i.recommended_action}`, action: { label: "Open queue", to: "/followups" }, duration: 9000 });
        } else if (fresh.length > 1) {
          notify({ tone: "info", title: `${fresh.length} new follow-ups need attention`,
            message: fresh.slice(0, 3).map((i) => `${i.participant_name} (${i.reason})`).join(", ") + (fresh.length > 3 ? ", …" : ""),
            action: { label: "Open queue", to: "/followups" }, duration: 9000 });
        }
      } catch { /* backend briefly unreachable: stay quiet, try again next tick */ }
    };
    void tick();
    const timer = setInterval(() => void tick(), POLL_MS);
    return () => { stopped = true; clearInterval(timer); };
  }, [eventId, notify]);
}
