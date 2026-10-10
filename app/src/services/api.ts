import type { Analytics, AppSettings, Campaign, CampaignInput, EventInfo, EventInput, ExotelReadiness, FollowUp, QueueItem, Recipient } from "../types";

export const API_BASE = (process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: { field: string; message: string }[]) { super(message); }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try { res = await fetch(`${API_BASE}/api${path}`, init); }
  catch { throw new ApiError(0, "network", `Cannot reach the backend at ${API_BASE}. Is it running?`); }
  if (!res.ok) {
    let body: { error?: { code: string; message: string; details?: { field: string; message: string }[] } } = {};
    try { body = await res.json(); } catch { /* non-JSON error */ }
    throw new ApiError(res.status, body.error?.code ?? "http_error", body.error?.message ?? res.statusText, body.error?.details ?? undefined);
  }
  return res.json() as Promise<T>;
}
const json = (method: string, body?: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body),
});
const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
};

/** A picked file: a web File/Blob, or the {uri,name,type} object that React Native FormData understands. */
export type FormDataValue = Blob | { uri: string; name: string; type: string };

export const api = {
  settings: () => req<AppSettings>("/settings"),
  exotelReadiness: () => req<ExotelReadiness>("/settings/exotel-readiness"),
  events: () => req<EventInfo[]>("/events"),
  createEvent: (b: EventInput) => req<EventInfo>("/events", json("POST", b)),
  analytics: (p: { eventId?: number; campaignId?: number; source?: string } = {}) =>
    req<Analytics>(`/analytics${qs({ event_id: p.eventId, campaign_id: p.campaignId, source: p.source && p.source !== "all" ? p.source : undefined })}`),
  campaigns: (eventId?: number) => req<Campaign[]>(`/campaigns${qs({ event_id: eventId })}`),
  campaign: (id: number) => req<Campaign>(`/campaigns/${id}`),
  createCampaign: (b: CampaignInput) => req<Campaign>("/campaigns", json("POST", b)),
  startCampaign: (id: number) => req<{ dispatched: number; skipped: unknown[] }>(`/campaigns/${id}/start`, json("POST")),
  cancelCampaign: (id: number) => req<Campaign>(`/campaigns/${id}/cancel`, json("POST")),
  retryDue: (id: number, force = false) => req<{ dispatched: number }>(`/campaigns/${id}/retry-due?force=${force}`, json("POST")),
  recipients: (cid: number) => req<Recipient[]>(`/campaigns/${cid}/recipients`),
  importRecipients: (cid: number, file: FormDataValue, consent: boolean) => {
    const fd = new FormData();
    fd.append("file", file as never);
    fd.append("consent_confirmed", String(consent));
    return req<{ imported: number; rejected: number; errors: { line: number; error: string }[] }>(`/campaigns/${cid}/recipients/import`, { method: "POST", body: fd });
  },
  optOut: (rid: number) => req<Recipient>(`/recipients/${rid}/opt-out`, json("POST")),
  participants: (p: { eventId?: number; filter?: string } = {}) =>
    req<Recipient[]>(`/recipients${qs({
      event_id: p.eventId, attention: p.filter === "attention" || undefined, retry_eligible: p.filter === "retry" || undefined,
      opted_out: p.filter === "optout" || undefined, outcome: p.filter === "callback" ? "callback_requested" : undefined })}`),
  followupQueue: (p: { eventId?: number } = {}) => req<QueueItem[]>(`/followups/queue${qs({ event_id: p.eventId })}`),
  patchFollowup: (id: number, b: { status?: string; scheduled_at?: string }) => req<FollowUp>(`/followups/${id}`, json("PATCH", b)),
  clarifyRecipient: (rid: number) => req<{ dispatched: number; skipped: { reason: string }[] }>(`/recipients/${rid}/clarify`, json("POST")),
};
