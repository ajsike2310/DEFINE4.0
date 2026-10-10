import type { BrowserCall, BrowserReply, VoiceStatus, Analytics, AppSettings, Attempt, Campaign, CampaignInput, CampaignOverview, Lead, LeadInput, LeadSummary, EventInfo, ExotelReadiness, EventInput, FollowUp, Intent, QueueItem, Recipient, RecipientHistory } from "../types";

// The compatible API of this project lives under /api/v2 (see dashboard/v2.py). Override with VITE_API_BASE.
const BASE: string = import.meta.env.VITE_API_BASE ?? "/api/v2";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: { field: string; message: string }[]) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "network", "Cannot reach the backend. Is it running?");
  }
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

/** Binary response (audio). Same error envelope as req(). */
async function reqBlob(path: string, init?: RequestInit): Promise<Blob> {
  let res: Response;
  try { res = await fetch(`${BASE}${path}`, init); } catch { throw new ApiError(0, "network", "Cannot reach the backend. Is it running?"); }
  if (!res.ok) {
    let body: { error?: { code: string; message: string } } = {};
    try { body = await res.json(); } catch { /* non-JSON error */ }
    throw new ApiError(res.status, body.error?.code ?? "http_error", body.error?.message ?? res.statusText);
  }
  return res.blob();
}

export const api = {
  voiceStatus: () => req<VoiceStatus>("/voice/status"),
  startBrowserCall: (cid: number, rid: number, mode: "main" | "clarify" = "main") =>
    req<BrowserCall>(`/campaigns/${cid}/recipients/${rid}/browser-call?mode=${mode}`, json("POST")),
  browserCallSpeech: (aid: number) => reqBlob(`/browser-calls/${aid}/speak`, json("POST")),
  browserCallSpeakReply: async (aid: number) => {
    // Same error envelope as reqBlob; also returns the exact words spoken (percent-encoded in a header) for captions.
    let res: Response;
    try { res = await fetch(`${BASE}/browser-calls/${aid}/speak-reply`, json("POST")); } catch { throw new ApiError(0, "network", "Cannot reach the backend. Is it running?"); }
    if (!res.ok) {
      let body: { error?: { code: string; message: string } } = {};
      try { body = await res.json(); } catch { /* non-JSON error */ }
      throw new ApiError(res.status, body.error?.code ?? "http_error", body.error?.message ?? res.statusText);
    }
    return { blob: await res.blob(), text: decodeURIComponent(res.headers.get("X-Spoken-Text") ?? "") };
  },
  browserCallRespond: (aid: number, b: { dtmf?: string; text?: string }) => req<BrowserReply>(`/browser-calls/${aid}/respond`, json("POST", b)),
  browserCallRespondAudio: (aid: number, audio: Blob) => {
    const fd = new FormData();
    fd.append("file", audio, "reply.webm");
    return req<BrowserReply>(`/browser-calls/${aid}/respond-audio`, { method: "POST", body: fd });
  },
  browserCallHangup: (aid: number) => req<{ attempt_id: number; status: string }>(`/browser-calls/${aid}/hangup`, json("POST")),
  settings: () => req<AppSettings>("/settings"),
  setVoicemail: (leave_message: boolean) => req<AppSettings>("/settings/voicemail", json("PUT", { leave_message })),
  setCallingHours: (b: { enabled: boolean; start: string; end: string }) => req<AppSettings>("/settings/calling-hours", json("PUT", b)),
  patchRecipient: (rid: number, b: { message?: string; preferred_language?: string }) => req<Recipient>(`/recipients/${rid}`, json("PATCH", b)),
  clarifyRecipient: (rid: number) => req<{ dispatched: number; skipped: { reason: string }[] }>(`/recipients/${rid}/clarify`, json("POST")),
  clarifyCampaign: (cid: number) => req<{ dispatched: number; skipped: { reason: string }[] }>(`/campaigns/${cid}/clarify`, json("POST")),
  exotelReadiness: () => req<ExotelReadiness>("/settings/exotel-readiness"),
  events: () => req<EventInfo[]>("/events"),
  event: (id: number) => req<EventInfo>(`/events/${id}`),
  createEvent: (b: EventInput) => req<EventInfo>("/events", json("POST", b)),
  updateEvent: (id: number, b: Partial<EventInput>) => req<EventInfo>(`/events/${id}`, json("PATCH", b)),
  followupQueue: (p: { eventId?: number; campaignId?: number } = {}) => {
    const q = new URLSearchParams();
    if (p.eventId) q.set("event_id", String(p.eventId));
    if (p.campaignId) q.set("campaign_id", String(p.campaignId));
    return req<QueueItem[]>(`/followups/queue?${q}`);
  },
  participants: (p: { eventId?: number; filter?: string } = {}) => {
    const q = new URLSearchParams();
    if (p.eventId) q.set("event_id", String(p.eventId));
    if (p.filter === "attention") q.set("attention", "true");
    if (p.filter === "retry") q.set("retry_eligible", "true");
    if (p.filter === "optout") q.set("opted_out", "true");
    if (p.filter === "callback") q.set("outcome", "callback_requested");
    return req<Recipient[]>(`/recipients?${q}`);
  },
  history: (rid: number) => req<RecipientHistory>(`/recipients/${rid}/history`),
  copyParticipants: (cid: number, src: number) =>
    req<{ copied: number; skipped: number }>(`/campaigns/${cid}/recipients/copy-from/${src}`, json("POST")),
  analytics: (p: { campaignId?: number; eventId?: number; source?: string } = {}) => {
    const q = new URLSearchParams();
    if (p.campaignId) q.set("campaign_id", String(p.campaignId));
    if (p.eventId) q.set("event_id", String(p.eventId));
    if (p.source && p.source !== "all") q.set("source", p.source);
    return req<Analytics>(`/analytics?${q}`);
  },
  campaigns: (eventId?: number) => req<Campaign[]>(`/campaigns${eventId ? `?event_id=${eventId}` : ""}`),
  campaign: (id: number) => req<Campaign>(`/campaigns/${id}`),
  createCampaign: (b: CampaignInput) => req<Campaign>("/campaigns", json("POST", b)),
  cancelCampaign: (id: number) => req<Campaign>(`/campaigns/${id}/cancel`, json("POST")),
  updateCampaign: (id: number, b: { name?: string; max_attempts?: number; messages?: Record<string, string>; auto_retry?: boolean; retry_interval_min?: number }) => req<Campaign>(`/campaigns/${id}`, json("PATCH", b)),
  deleteCampaign: (id: number) => req<{ deleted: number }>(`/campaigns/${id}`, json("DELETE")),
  scheduleCampaign: (id: number, scheduledAt: string) => req<Campaign>(`/campaigns/${id}/schedule`, json("POST", { scheduled_at: scheduledAt })),
  unscheduleCampaign: (id: number) => req<Campaign>(`/campaigns/${id}/unschedule`, json("POST")),
  startCampaign: (id: number) => req<{ dispatched: number; skipped: unknown[] }>(`/campaigns/${id}/start`, json("POST")),
  retryDue: (id: number, force = false) => req<{ dispatched: number }>(`/campaigns/${id}/retry-due?force=${force}`, json("POST")),
  recipients: (cid: number) => req<Recipient[]>(`/campaigns/${cid}/recipients`),
  allRecipients: (p: { outcome?: string; language?: string } = {}) => {
    const q = new URLSearchParams();
    if (p.outcome) q.set("outcome", p.outcome);
    if (p.language) q.set("language", p.language);
    return req<Recipient[]>(`/recipients?${q}`);
  },
  addRecipient: (cid: number, b: { name: string; phone: string; external_ref?: string | null; preferred_language?: string | null; consent_status: string; message?: string }) =>
    req<Recipient>(`/campaigns/${cid}/recipients`, json("POST", b)),
  importRecipients: (cid: number, file: File, consent: boolean) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("consent_confirmed", String(consent));
    return req<{ imported: number; rejected: number; errors: { line: number; error: string }[] }>(
      `/campaigns/${cid}/recipients/import`, { method: "POST", body: fd });
  },
  optOut: (rid: number) => req<Recipient>(`/recipients/${rid}/opt-out`, json("POST")),
  attempts: (cid: number) => req<Attempt[]>(`/campaigns/${cid}/attempts`),
  intents: (cid: number) => req<Intent[]>(`/campaigns/${cid}/intents`),
  followups: (p: { campaignId?: number; status?: string } = {}) => {
    const q = new URLSearchParams();
    if (p.campaignId) q.set("campaign_id", String(p.campaignId));
    if (p.status) q.set("status", p.status);
    return req<FollowUp[]>(`/followups?${q}`);
  },
  patchFollowup: (id: number, b: { status?: string; scheduled_at?: string }) => req<FollowUp>(`/followups/${id}`, json("PATCH", b)),
  campaignOverview: (eventId?: number) => req<CampaignOverview>(`/campaigns/overview${eventId ? `?event_id=${eventId}` : ""}`),
  duplicateCampaign: (id: number, b: { name?: string; copy_participants: boolean }) =>
    req<{ campaign: Campaign; copied: number; skipped: number }>(`/campaigns/${id}/duplicate`, json("POST", b)),
  leads: (eventId: number, p: { status?: string; source?: string; q?: string } = {}) => {
    const q = new URLSearchParams();
    if (p.status) q.set("status", p.status);
    if (p.source) q.set("source", p.source);
    if (p.q) q.set("q", p.q);
    return req<Lead[]>(`/events/${eventId}/leads?${q}`);
  },
  leadSummary: (eventId: number) => req<LeadSummary>(`/events/${eventId}/leads/summary`),
  captureLead: (eventId: number, b: LeadInput) => req<Lead>(`/events/${eventId}/leads`, json("POST", b)),
  importLeads: (eventId: number, file: File, consent: boolean) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("consent_confirmed", String(consent));
    return req<{ imported: number; rejected: number; errors: { line: number; error: string }[] }>(
      `/events/${eventId}/leads/import`, { method: "POST", body: fd });
  },
  patchLead: (id: number, b: { status?: string; notes?: string; consent_status?: string }) => req<Lead>(`/leads/${id}`, json("PATCH", b)),
  convertLeads: (campaignId: number, leadIds: number[]) =>
    req<{ converted: number; skipped: { lead_id: number; reason: string }[] }>("/leads/convert", json("POST", { campaign_id: campaignId, lead_ids: leadIds })),
  seedSampleLeads: () => req<{ leads_added: number }>("/demo/seed-leads", json("POST")),
  seedDemo: () => req<Campaign>("/demo/seed", json("POST")),
  seedAll: (run: boolean) => req<{ ran: boolean; campaigns: Campaign[]; events: EventInfo[] }>(`/demo/seed-all?run=${run}`, json("POST")),
  resetDemo: () => req<{ deleted_campaigns: number }>("/demo", json("DELETE")),
};
