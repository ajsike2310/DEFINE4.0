import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check } from "lucide-react";
import { api, ApiError } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { Button, Card, Field, PageHeader, inputCls } from "../components/ui";
import { NoEvent } from "../components/NoEvent";
import { LANG_LABEL, PURPOSE_LABEL } from "../services/labels";

const OPT = "If you would like us to stop calling you, just tell us.";
const PLACEHOLDER = "[ORGANISER: add verified details]";
const TEMPLATES: Record<string, { en: (e: string) => string; ml?: (e: string) => string }> = {
  attendance_confirmation: {
    en: (e) => `Hello, this is Cadence calling on behalf of ${e} to confirm your attendance. Will you be able to attend? You can also ask us to call you back, or ask a question. ${OPT}`,
    ml: (e) => `നമസ്കാരം, ${e}-ന് വേണ്ടി Cadence വിളിക്കുന്നു. നിങ്ങളുടെ പങ്കാളിത്തം സ്ഥിരീകരിക്കാൻ വിളിക്കുകയാണ്. നിങ്ങൾക്ക് പങ്കെടുക്കാൻ കഴിയുമോ? തിരികെ വിളിക്കണമെങ്കിലോ എന്തെങ്കിലും ചോദിക്കാനുണ്ടെങ്കിലോ അതും പറയാം. ഇനി ഞങ്ങൾ വിളിക്കേണ്ടെങ്കിൽ അത് പറഞ്ഞാൽ മതി.`,
  },
  event_announcement: { en: (e) => `Hello, this is Cadence calling on behalf of ${e} with an announcement: ${PLACEHOLDER}. Please let us know you have heard this, or tell us if you have a question or would like a call back. ${OPT}` },
  schedule_venue_update: { en: (e) => `Hello, this is Cadence calling on behalf of ${e} with a schedule or venue update: ${PLACEHOLDER}. Please let us know you have heard this, or tell us if you have a question. ${OPT}` },
  submission_deadline_reminder: { en: (e) => `Hello, this is Cadence calling on behalf of ${e} with a reminder about the submission deadline: ${PLACEHOLDER}. Please let us know you have heard this, or tell us if you have a question. ${OPT}` },
  participant_followup: { en: (e) => `Hello, this is Cadence calling on behalf of ${e}. ${PLACEHOLDER}. Please let us know you have heard this, or tell us if you have a question or would like a call back. ${OPT}` },
};
const STEPS = ["Purpose", "Message", "Participants", "Review"];

export default function NewCampaign() {
  const nav = useNavigate();
  const { selected } = useEvent();
  const existing = useAsync(() => (selected ? api.campaigns(selected.id) : Promise.resolve([])), [selected?.id]);
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("attendance_confirmation");
  const [languages, setLanguages] = useState<string[]>(["en"]);
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [when, setWhen] = useState("");   // datetime-local value; empty = no schedule
  const [copyFrom, setCopyFrom] = useState<number | "">("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  // Progress of a partly finished submit, so a retry resumes instead of creating a duplicate campaign.
  const created = useRef<{ id: number; imported: boolean; copied: boolean; scheduled?: boolean; notes: string[] } | null>(null);

  const evName = selected?.name ?? "the event";
  const msgFor = (l: string) => messages[l] ?? (l === "en" ? TEMPLATES[purpose].en(evName) : TEMPLATES[purpose].ml?.(evName) ?? "");
  const hasParticipants = !!file || copyFrom !== "";

  function validate(s: number) {
    const e: Record<string, string> = {};
    if (s === 0 && name.trim().length < 2) e.name = "Enter a campaign name (at least 2 characters).";
    if (s === 0 && languages.length === 0) e.languages = "Select at least one language.";
    if (s === 1) languages.forEach((l) => {
      const m = msgFor(l).trim();
      if (!m) e[`msg_${l}`] = `Message required for ${LANG_LABEL[l]}.`;
      else if (m.includes("[ORGANISER")) e[`msg_${l}`] = "Replace the bracketed placeholder with details you have verified.";
    });
    if (s === 2 && file && !consent) e.consent = "Confirm you have consent to call these contacts, or remove the file.";
    setErrors(e);
    return Object.keys(e).length === 0;
  }
  const next = () => validate(step) && setStep(step + 1);

  async function submit(launch: boolean, schedule = false) {
    if (busy || !selected) return;          // guards against double-click duplicate creation/launch
    if (!validate(1) || !validate(2)) return;
    if (schedule && !(when && new Date(when).getTime() > Date.now())) { setResult("Choose a start time in the future."); return; }
    setBusy(true); setResult(null);
    try {
      if (!created.current) {
        const c = await api.createCampaign({ event_id: selected.id, name: name.trim(), purpose, languages, max_attempts: maxAttempts,
          require_consent: true, messages: Object.fromEntries(languages.map((l) => [l, msgFor(l)])) });
        created.current = { id: c.id, imported: false, copied: false, notes: [] };
      }
      const c = created.current;
      if (file && !c.imported) {
        const r = await api.importRecipients(c.id, file, consent);
        c.imported = true;
        c.notes.push(`${r.imported} imported${r.rejected ? `, ${r.rejected} rejected (${r.errors.slice(0, 3).map((x) => `line ${x.line}: ${x.error}`).join("; ")})` : ""}`);
      }
      if (copyFrom !== "" && !c.copied) {
        const r = await api.copyParticipants(c.id, copyFrom);
        c.copied = true;
        c.notes.push(`${r.copied} copied, ${r.skipped} skipped (opted out / revoked / duplicate)`);
      }
      if (schedule && !c.scheduled) {
        const at = new Date(when);
        await api.scheduleCampaign(c.id, at.toISOString());
        c.scheduled = true;
        c.notes.push(`scheduled for ${at.toLocaleString()}`);
      }
      if (launch) {
        const r = await api.startCampaign(c.id);
        c.notes.push(`${r.dispatched} call(s) dispatched, ${r.skipped.length} skipped`);
      }
      const notes = c.notes;
      if (notes.length) sessionStorage.setItem(`note-${c.id}`, notes.join(" · "));
      nav(`/campaigns/${c.id}`);
    } catch (e) {
      const why = e instanceof ApiError && e.details ? e.details.map((d) => `${d.field}: ${d.message}`).join(" · ") : (e as Error).message;
      setResult(created.current ? `${why} The draft campaign was already saved; pressing the button again continues from where it stopped.` : why);
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="New campaign" subtitle={selected ? `For ${selected.name}. Saved as a draft unless you choose to launch. You can also schedule a start time on the last step.` : undefined} />
      <NoEvent />
      {selected && (<>
        <ol className="mb-7 flex items-center" aria-label="Progress">
          {STEPS.map((s, i) => (
            <li key={s} aria-current={i === step ? "step" : undefined} className="flex items-center">
              <span className={`grid h-6 w-6 place-items-center rounded-full border text-xs font-semibold transition-colors duration-300 ${i < step ? "border-brand bg-brand text-white" : i === step ? "border-brand bg-surface text-brand" : "border-line bg-surface text-muted"}`}>
                {i < step ? <Check className="h-3.5 w-3.5" /> : i + 1}</span>
              <span className={`ml-2 text-[13px] ${i === step ? "font-medium text-ink" : "hidden text-muted sm:inline"}`}>{s}</span>
              {i < STEPS.length - 1 && <span aria-hidden className="mx-2 h-px w-6 overflow-hidden bg-line sm:mx-3 sm:w-14"><i className="block h-full bg-brand transition-[width] duration-500" style={{ width: i < step ? "100%" : "0%" }} /></span>}
            </li>))}
        </ol>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]"><Card>
          <div className="max-w-xl space-y-4">
            <div key={step} className="expand-in space-y-4">{step === 0 && (<>
              <Field label="Campaign name" error={errors.name}><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <Field label="Purpose">
                <select className={inputCls} value={purpose} onChange={(e) => { setPurpose(e.target.value); setMessages({}); }}>
                  {Object.entries(PURPOSE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>
              <fieldset>
                <legend className="mb-1 text-sm font-medium">Languages</legend>
                {["en", "ml"].map((k) => (
                  <label key={k} className="mr-4 text-sm"><input type="checkbox" className="mr-1" checked={languages.includes(k)}
                    onChange={(e) => setLanguages((ls) => e.target.checked ? [...ls, k] : ls.filter((x) => x !== k))} />{LANG_LABEL[k]}</label>))}
                <p className="mt-1 text-xs text-muted">Malayalam understanding is rule-based and experimental. The first language is the default for participants without a preference.</p>
                {errors.languages && <p role="alert" className="drop-in text-xs font-medium text-bad">{errors.languages}</p>}
              </fieldset>
              <Field label="Max call attempts per participant" hint="Only failed, busy, unanswered or voicemail calls are retried."><input type="number" min={1} max={5} className={inputCls} value={maxAttempts} onChange={(e) => setMaxAttempts(Math.min(5, Math.max(1, Math.round(Number(e.target.value)) || 1)))} /></Field>
            </>)}
            {step === 1 && languages.map((l) => (
              <Field key={l} label={`Message — ${LANG_LABEL[l]}`} error={errors[`msg_${l}`]}
                hint={l === "ml" && !TEMPLATES[purpose].ml ? "No sample Malayalam text for this purpose; write or paste your reviewed message." : undefined}>
                <textarea rows={5} className={inputCls} value={msgFor(l)} onChange={(e) => setMessages({ ...messages, [l]: e.target.value })} />
              </Field>))}
            {step === 2 && (<>
              <Field label="Import participants from CSV" hint="Columns: name, phone (E.164, e.g. +919876543210). Optional: participant_id, language, segment, opted_out (yes = never call).">
                <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </Field>
              <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                <span>I confirm these contacts are an authorised list and have agreed to receive calls of this kind.</span></label>
              {errors.consent && <p role="alert" className="drop-in text-xs font-medium text-bad">{errors.consent}</p>}
              <Field label="…or reuse participants from another campaign of this event" hint="Opted-out and consent-revoked participants are never copied.">
                <select className={inputCls} value={copyFrom} onChange={(e) => setCopyFrom(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">None</option>
                  {(existing.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name} ({c.recipient_count})</option>)}
                </select>
              </Field>
              <p className="text-xs text-muted">Without confirmed consent, participants are stored as “unknown” and skipped at launch. You can also add people one by one on the campaign page.</p>
            </>)}
            {step === 3 && (
              <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
                <dt className="text-muted">Event</dt><dd>{selected.name}</dd>
                <dt className="text-muted">Name</dt><dd>{name}</dd>
                <dt className="text-muted">Purpose</dt><dd>{PURPOSE_LABEL[purpose]}</dd>
                <dt className="text-muted">Languages</dt><dd>{languages.map((l) => LANG_LABEL[l]).join(", ")}</dd>
                <dt className="text-muted">Attempts</dt><dd>up to {maxAttempts}</dd>
                <dt className="text-muted">Participants</dt><dd>{[file && `${file.name} (consent ${consent ? "confirmed" : "not confirmed"})`, copyFrom !== "" && `copy from campaign #${copyFrom}`].filter(Boolean).join(" + ") || "none yet"}</dd>
                <dt className="text-muted">Start</dt><dd>{when ? new Date(when).toLocaleString() : "Draft, launched by you"}</dd>
                <dt className="text-muted">Calling</dt><dd>{selected.is_demo ? "Simulated (sample event)" : "Per backend provider setting; see Settings"}</dd>
              </dl>)}
            </div>{result && <p role="alert" className="drop-in text-sm font-medium text-bad">{result}</p>}
            <div className="flex flex-wrap gap-2 pt-2">
              {step > 0 && <Button variant="secondary" disabled={busy} onClick={() => setStep(step - 1)}>Back</Button>}
              {step < 3 ? <Button onClick={next}>Continue</Button> : (<>
                <Button variant="secondary" disabled={busy} onClick={() => submit(false)}>{busy ? "Working…" : "Create draft"}</Button>
                <Button disabled={busy || !hasParticipants} title={hasParticipants ? undefined : "Add participants first"} onClick={() => submit(true)}>{busy ? "Working…" : "Create and launch now"}</Button>
                <Button variant="secondary" disabled={busy || !hasParticipants || !when} title={!hasParticipants ? "Add participants first" : !when ? "Choose a start time first" : undefined} onClick={() => submit(false, true)}>{busy ? "Working…" : "Create and schedule"}</Button>
              </>)}
            </div>
            {step === 3 && (
              <Field label="Start automatically at (optional)" hint="Your local time. Needs participants. The backend scheduler starts the campaign at this time.">
                <input type="datetime-local" className={inputCls} value={when} onChange={(e) => setWhen(e.target.value)} />
              </Field>)}
            {step === 3 && !hasParticipants && <p className="text-xs text-muted">Launch is disabled until participants are added (CSV or reuse).</p>}
          </div>
        </Card>
        <aside className="reveal h-fit rounded-lg border border-line bg-surface p-5 lg:sticky lg:top-20" aria-label="Campaign summary" style={{ "--i": 2 } as React.CSSProperties}>
          <h2 className="text-xs font-semibold text-ink-2">Your campaign so far</h2>
          <dl className="mt-4 space-y-3 text-[13px]">
            {([["Event", selected.name], ["Name", name.trim() || "—"], ["Purpose", PURPOSE_LABEL[purpose]],
               ["Languages", languages.map((l) => LANG_LABEL[l]).join(", ") || "—"], ["Attempts", `up to ${maxAttempts}`],
               ["Participants", [file && file.name, copyFrom !== "" && `reuse #${copyFrom}`].filter(Boolean).join(" + ") || "not added yet"]] as [string, string][]).map(([k, v]) => (
              <div key={k}><dt className="text-xs text-muted">{k}</dt><dd className="mt-0.5 break-words text-ink">{v}</dd></div>))}
          </dl>
          <p className="mt-4 border-t border-line-soft pt-3 text-xs leading-relaxed text-muted">Nothing is called until you launch. Participants without confirmed consent, or who opted out, are skipped automatically.</p>
        </aside>        </div>
      </>)}
    </>
  );
}
