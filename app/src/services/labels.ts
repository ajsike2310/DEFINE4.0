export const PURPOSE_LABEL: Record<string, string> = {
  attendance_confirmation: "Attendance confirmation", event_announcement: "Event announcement",
  schedule_venue_update: "Schedule or venue update", submission_deadline_reminder: "Submission deadline reminder",
  participant_followup: "Participant follow-up",
};
export const OUTCOME_LABEL: Record<string, string> = {
  acknowledged: "Acknowledged", pending: "Pending", confirmed: "Attending (confirmed)", declined: "Declined", callback_requested: "Callback requested",
  information_requested: "Info requested", unclear: "Unclear", human_required: "Needs human",
  opted_out: "Opted out", no_response: "Not reached",
};
export const CALL_LABEL: Record<string, string> = {
  queued: "Queued", initiating: "Initiating", ringing: "Ringing", answered: "Answered", completed: "Completed",
  failed: "Failed", busy: "Busy", no_answer: "No answer", voicemail: "Voicemail", cancelled: "Cancelled",
};
export const LANG_LABEL: Record<string, string> = { en: "English", ml: "Malayalam", unspecified: "Unspecified" };

export type Tone = "good" | "bad" | "warn" | "neutral" | "info";
export const OUTCOME_TONE: Record<string, Tone> = {
  confirmed: "good", acknowledged: "good", declined: "bad", callback_requested: "info", information_requested: "info",
  unclear: "warn", human_required: "warn", opted_out: "bad", no_response: "neutral", pending: "neutral",
};
export const CALL_TONE: Record<string, Tone> = {
  completed: "good", answered: "good", failed: "bad", busy: "warn", no_answer: "warn", voicemail: "warn",
  queued: "neutral", initiating: "info", ringing: "info", cancelled: "neutral",
};

export const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 1000) / 10}%`);
export const maskPhone = (p: string) => (p.length <= 6 ? "•".repeat(Math.max(p.length - 2, 0)) + p.slice(-2) : p.slice(0, 3) + "•".repeat(p.length - 5) + p.slice(-2));
export const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleString() : "—");

export const CAMPAIGN_LABEL: Record<string, string> = {
  draft: "Draft", scheduled: "Scheduled", running: "Running", completed: "Completed", cancelled: "Cancelled",
};
export const CAMPAIGN_TONE: Record<string, Tone> = {
  draft: "neutral", scheduled: "info", running: "warn", completed: "good", cancelled: "bad",
};
