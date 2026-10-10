export interface EventInfo {
  id: number; name: string; description: string; approved_info: Record<string, string>;
  organizer_contact: string | null; is_demo: boolean; campaign_count: number;
}
export interface EventInput {
  name: string; description?: string; approved_info: Record<string, string>; organizer_contact?: string | null;
}
export interface QueueItem {
  followup_id: number; campaign_id: number; campaign_name: string; event_id: number; recipient_id: number;
  participant_name: string; participant_ref: string | null; participant_phone?: string; reason: string; action_type: string; status: string;
  priority: number; priority_reason: string; latest_outcome: string; recommended_action: string;
  can_clarify: boolean; clarification_attempted: boolean;
  scheduled_at: string | null; note: string; is_simulated: boolean; created_at: string;
}
export interface RecipientHistory {
  recipient: Recipient; attempts: Attempt[]; intents: Intent[]; followups: FollowUp[];
}
export interface Campaign {
  id: number; event_id: number; name: string; purpose: string; messages: Record<string, string>; languages: string[];
  status: string; scheduled_at: string | null; max_attempts: number; require_consent: boolean;
  is_demo: boolean; created_at: string; updated_at: string; recipient_count: number;
  auto_retry?: boolean; retry_interval_min?: number;
}
export interface Recipient {
  id: number; campaign_id: number; external_ref: string | null; name: string; phone: string; preferred_language: string | null;
  segment: string | null; consent_status: string; opted_out: boolean; outcome: string; is_demo: boolean;
  message?: string; attempts?: number; next_attempt_at?: string | null; rsvp?: string; can_call?: boolean; error?: string;
}
export interface Attempt {
  id: number; campaign_id: number; recipient_id: number; provider: string; is_simulated: boolean;
  provider_call_id: string | null; attempt_number: number; mode: string; call_language: string; status: string;
  started_at: string | null; answered_at: string | null; completed_at: string | null;
  failure_reason: string | null; next_retry_at: string | null;
}
export interface Intent {
  id: number; call_attempt_id: number; recipient_id: number; intent: string; score: number; method: string;
  detected_language: string; evidence: string; notes: string[]; needs_review: boolean; next_action: string;
}
export interface FollowUp {
  id: number; campaign_id: number; recipient_id: number; action_type: string; status: string;
  scheduled_at: string | null; note: string; created_at: string;
}
export interface Analytics {
  source: string;
  totals: Record<string, number>;
  outcomes: Record<string, number>;
  followups: { pending: number; completed: number; cancelled: number };
  rates: Record<string, number | null>;
  by_language: ({ language: string; recipients: number; attempts: number; answered: number } & Record<string, number | string>)[];
  needs_review: number; needs_attention: number;
  headcount: Headcount | null;
  clarification: { attempted: number; resolved: number };
}
export interface Headcount {
  participants: number; confirmed: number; declined: number; unknown: number;
  unknown_breakdown: Record<string, number>; floor: number; ceiling: number; certainty: number;
}
export interface ExotelReadiness {
  ready: boolean; checks: { name: string; ok: boolean; required: boolean; detail?: string }[];
  urls: { status_callback: string | null; passthru_response: string | null }; note: string;
}
export interface AppSettings {
  provider: string; exotel_configured: boolean;
  languages: { code: string; name: string; support: string }[];
  retry_policy: { max_attempts_default: number; backoff_minutes: number; retry_on: string[] };
  data_location: string; transcription: string;
  voicemail?: { leave_message: boolean };
  calling_hours?: { enabled: boolean; start: string; end: string }; now_local?: string; timezone?: string;
}
export interface CampaignInput {
  event_id: number; name: string; purpose: string; messages: Record<string, string>; languages: string[];
  max_attempts: number; require_consent: boolean; scheduled_at?: string | null; auto_retry?: boolean; retry_interval_min?: number;
}

export interface Lead {
  id: number; event_id: number; name: string; phone: string; email: string | null; source: string;
  interest: string | null; preferred_language: string | null; consent_status: string; status: string;
  notes: string; recipient_id: number | null; is_demo: boolean; created_at: string;
  score: number; score_reasons: string[]; campaign_id: number | null; recipient_outcome: string | null;
}
export interface LeadInput {
  name: string; phone: string; email?: string | null; source: string; interest?: string | null;
  preferred_language?: string | null; consent_status: string; notes?: string;
}
export interface LeadSummary {
  total: number; by_status: Record<string, number>; consented: number; consent_rate: number | null;
  conversion_rate: number | null; ready_to_convert: number;
  by_source: { source: string; leads: number; converted: number; consented: number; conversion_rate: number }[];
}
export interface CampaignRow {
  campaign_id: number; event_id: number; name: string; purpose: string; status: string; is_demo: boolean;
  participants: number; contacted: number; resolved: number; needs_attention: number; retry_eligible: number;
  missing_consent: number; progress: number | null; next_step: string; created_at: string;
}
export interface CampaignOverview {
  by_status: Record<string, number>; campaigns: CampaignRow[];
  totals: { participants: number; needs_attention: number; retry_eligible: number };
}
export interface VoiceStatus { configured: boolean; voice_id: string; tts_model: string; stt_model: string; note: string }
export interface BrowserCall { attempt_id: number; status: string; mode: string; language: string; message: string; simulated: boolean; participant: string }
export interface BrowserReply {
  attempt_id: number; status: string; heard: string | null; outcome: string; simulated: boolean; intent: string | null;
  method: string | null; next: "clarify" | "close"; next_action: string | null; needs_review: boolean | null; evidence: string | null; notes: string[];
}
