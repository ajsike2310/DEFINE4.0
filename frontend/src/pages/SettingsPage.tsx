import { useState, type ReactNode } from "react";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { useNotify } from "../hooks/useNotify";
import { SampleButtons } from "../components/NoEvent";
import { getFollowupAlerts, setFollowupAlerts } from "../hooks/useQueueWatcher";
import { Badge, Button, ErrorState, Loading } from "../components/ui";

/** One setting: label and help on the left, the value or control on the right. */
function Row({ label, help, children }: { label: string; help?: ReactNode; children?: ReactNode }) {
  return (
    <div className="grid gap-x-8 gap-y-2 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] sm:items-start">
      <div className="min-w-0">
        <div className="text-[13.5px] font-medium text-ink">{label}</div>
        {help && <div className="mt-0.5 text-[12.5px] leading-relaxed text-muted">{help}</div>}
      </div>
      <div className="min-w-0 text-[13.5px] text-ink-2 sm:justify-self-end sm:text-right">{children}</div>
    </div>
  );
}

function Section({ id, title, description, children }: { id: string; title: string; description?: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-24">
      <h2 id={`${id}-h`} className="text-[16px] font-semibold text-ink">{title}</h2>
      {description && <p className="mt-0.5 text-[13px] text-muted">{description}</p>}
      <div className="mt-3 divide-y divide-line-soft rounded-lg border border-line bg-surface">{children}</div>
    </section>
  );
}

function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
      className={`press relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${checked ? "bg-ink" : "bg-line"}`}>
      <span aria-hidden className={`inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-[22px]" : "translate-x-0.5"}`} />
    </button>
  );
}

function VoiceRows() {
  const { data, error } = useAsync(() => api.voiceStatus(), []);
  return (<>
    <Row label="Voice (ElevenLabs)" help="Speaks the script and transcribes a spoken reply in the browser demo call. It is not a phone line, and these calls are always recorded as simulated.">
      {error ? <span className="text-bad">{error.message}</span> : data && <Badge tone={data.configured ? "good" : "warn"}>{data.configured ? "Key set" : "Key not set"}</Badge>}
    </Row>
    {data && (<>
      <Row label="Voice id"><span className="break-all tabular-nums">{data.voice_id}</span></Row>
      <Row label="Speech model">{data.tts_model}</Row>
      <Row label="Transcription model">{data.stt_model}</Row>
      {!data.configured && <Row label="To turn voice on" help="Add ELEVENLABS_API_KEY to the backend .env file and restart the backend. The key is never shown here." />}
    </>)}
  </>);
}

function ExotelRows() {
  const { data, error, reload } = useAsync(() => api.exotelReadiness(), []);
  return (<>
    <Row label="Exotel readiness" help="Checks that the real phone provider is configured. Secrets are never shown here.">
      {data && <Badge tone={data.ready ? "good" : "warn"}>{data.ready ? "Ready for a test call" : "Not ready"}</Badge>}
    </Row>
    {error && <div className="px-5 py-4"><ErrorState error={error} retry={reload} /></div>}
    {data && (<>
      {data.checks.map((c) => (
        <Row key={c.name} label={c.name} help={!c.required ? "Optional" : undefined}>
          <span aria-hidden className={c.ok ? "font-semibold text-good" : "text-muted"}>{c.ok ? "✓ Set" : "○ Missing"}</span>
          <span className="sr-only">{c.ok ? "set" : "missing"}</span>
        </Row>
      ))}
      <Row label="Passthru URL"><code className="break-all text-xs">{data.urls.passthru_response ?? "set PUBLIC_BASE_URL first"}</code></Row>
      <Row label="StatusCallback URL"><code className="break-all text-xs">{data.urls.status_callback ?? "set PUBLIC_BASE_URL first"}</code></Row>
      <Row label="Note" help={<>{data.note} Values are set in <code>.env</code>.</>} />
    </>)}
  </>);
}

const NAV: [string, string][] = [["calling", "Calling"], ["notifications", "Notifications"], ["language", "Language and retries"], ["data", "Data"]];

export default function SettingsPage() {
  const { reload: reloadEvents } = useEvent();
  const reload = () => { void reloadEvents(); };
  const { data: s, error, loading, reload: reloadSettings } = useAsync(() => api.settings(), []);
  const { notify, success, error: fail, confirm } = useNotify();
  const [alerts, setAlerts] = useState(getFollowupAlerts);
  async function removeSamples() {
    const yes = await confirm({ title: "Remove all sample data?", message: "Deletes the sample events with their campaigns, participants and results. Events you created yourself are not touched.", confirmLabel: "Remove sample data", danger: true });
    if (!yes) return;
    try { const r = await api.resetDemo(); reload(); success("Sample data removed", `${r.deleted_campaigns} campaign${r.deleted_campaigns === 1 ? "" : "s"} deleted.`); }
    catch (e) { fail("Could not remove sample data", (e as Error).message); }
  }
  return (
    <>
      <div className="mb-6 border-b border-line pb-5">
        <h1 className="text-[24px] font-semibold leading-tight tracking-[-0.02em]">Settings</h1>
        <p className="mt-1.5 text-[13.5px] text-muted">Backend values are read-only here. Change them in the backend <code>.env</code> file and restart.</p>
      </div>
      {loading && !s && <Loading />}
      {error && <ErrorState error={error} retry={reloadSettings} />}
      {s && (
        <div className="grid gap-8 lg:grid-cols-[11rem_minmax(0,1fr)]">
          <nav aria-label="Settings sections" className="flex gap-1 overflow-x-auto lg:sticky lg:top-24 lg:flex-col lg:self-start">
            {NAV.map(([id, label]) => (
              <a key={id} href={`#${id}`} className="whitespace-nowrap rounded-md px-3 py-1.5 text-[13.5px] text-ink-2 hover:bg-line-soft hover:text-ink">{label}</a>
            ))}
          </nav>

          <div className="min-w-0 max-w-3xl space-y-10">
            <Section id="calling" title="Calling" description="How calls are placed and spoken.">
              <Row label="Calling provider" help={s.provider === "demo" ? "Demo provider: calls are simulated and deterministic. No phone is dialled." :
                `Exotel credentials configured: ${s.exotel_configured ? "yes" : "no"}. Real operation is unverified in this build.`}>
                <Badge tone={s.provider === "demo" ? "warn" : "good"}>{s.provider}</Badge>
              </Row>
              <VoiceRows />
              <ExotelRows />
            </Section>

            <Section id="notifications" title="Notifications" description="How the app tells you about new work.">
              <Row label="Alert me when new follow-ups arrive" help="Checks the follow-up queue every 15 seconds while this tab is open and shows a notification for anything new. Past notifications are kept under the bell.">
                <Switch checked={alerts} label="Alert me when new follow-ups arrive" onChange={(v) => { setAlerts(v); setFollowupAlerts(v); }} />
              </Row>
              <Row label="Preview a notification" help="See how each kind looks. Previews are not saved.">
                <div className="flex flex-wrap gap-2 sm:justify-end">
                  <Button variant="secondary" onClick={() => notify({ tone: "success", title: "Campaign started", message: "11 calls placed; 0 skipped.", keep: false })}>Success</Button>
                  <Button variant="secondary" onClick={() => notify({ tone: "info", title: "New follow-up: Sample Participant 3", message: "callback requested. Call back at their requested time.", action: { label: "Open queue", to: "/followups" }, keep: false })}>Information</Button>
                  <Button variant="secondary" onClick={() => notify({ tone: "warn", title: "No calls were placed", message: "Everyone was skipped: no consent, opted out, or already resolved.", keep: false })}>Warning</Button>
                  <Button variant="secondary" onClick={() => notify({ tone: "error", title: "That did not work", message: "Cannot reach the backend. Is it running on port 8000?", keep: false })}>Error</Button>
                </div>
              </Row>
            </Section>

            <Section id="language" title="Language and retries" description="What the calls can speak and how failed calls are retried.">
              {s.languages.map((l) => <Row key={l.code} label={l.name} help="Supported language"><span className="text-muted">{l.support}</span></Row>)}
              <Row label="Speech transcription">{s.transcription}</Row>
              <Row label="Retry policy" help="Never after a participant responds or opts out.">
                Up to {s.retry_policy.max_attempts_default} attempts, {s.retry_policy.backoff_minutes} min apart. Retried only on: {s.retry_policy.retry_on.join(", ")}.
              </Row>
            </Section>

            <Section id="data" title="Data" description="Where information is kept, and sample data for demos.">
              <Row label="Data location">{s.data_location}</Row>
              <Row label="Sample data (DEFINE 4.0 scenario)" help="Creates or removes a clearly labelled sample event with fictional participants and simulated, scripted calls. It is a demonstration scenario only; the real DEFINE 4.0 organisers have not requested or adopted Cadence.">
                <div className="flex flex-col gap-3 sm:items-end">
                  <SampleButtons />
                  <Button variant="danger" onClick={removeSamples}>Remove all sample data</Button>
                </div>
              </Row>
            </Section>
          </div>
        </div>
      )}
    </>
  );
}
