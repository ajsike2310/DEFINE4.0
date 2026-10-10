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
}
export interface Recipient {
  id: number; campaign_id: number; external_ref: string | null; name: string; phone: string; preferred_language: string | null;
  segment: string | null; consent_status: string; opted_out: boolean; outcome: string; is_demo: boolean;
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
}
export interface CampaignInput {
  event_id: number; name: string; purpose: string; messages: Record<string, string>; languages: string[];
  max_attempts: number; require_consent: boolean; scheduled_at?: string | null;
}
