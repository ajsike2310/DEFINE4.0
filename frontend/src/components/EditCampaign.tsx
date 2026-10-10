import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { Button, ErrorState, Field, Loading, inputCls } from "./ui";
import { LANG_LABEL } from "../services/labels";

/** Edit a draft or scheduled campaign: name, attempts and the message per language. Running and finished campaigns are locked. */
export function EditCampaignDialog({ campaignId, onClose }: { campaignId: number; onClose: (saved: boolean) => void }) {
  const { data: c, error, loading } = useAsync(() => api.campaign(campaignId), [campaignId]);
  const [name, setName] = useState("");
  const [attempts, setAttempts] = useState(3);
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [retry, setRetry] = useState("30");   // "off" or minutes between automatic retries
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const seeded = useRef(false);

  useEffect(() => {
    if (c && !seeded.current) { seeded.current = true; setName(c.name); setAttempts(c.max_attempts); setMessages(c.messages); setRetry(c.auto_retry === false ? "off" : String(c.retry_interval_min ?? 30)); }
  }, [c]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save() {
    if (!c || busy) return;
    const e: Record<string, string> = {};
    if (name.trim().length < 2) e.name = "Enter a campaign name (at least 2 characters).";
    for (const l of c.languages) {
      const m = (messages[l] ?? "").trim();
      if (!m) e[`msg_${l}`] = `Message required for ${LANG_LABEL[l] ?? l}.`;
      else if (m.includes("[ORGANISER")) e[`msg_${l}`] = "Replace the bracketed placeholder with details you have verified.";
    }
    setErrs(e);
    if (Object.keys(e).length) return;
    setBusy(true); setMsg(null);
    try {
      await api.updateCampaign(c.id, { name: name.trim(), max_attempts: attempts, auto_retry: retry !== "off", retry_interval_min: retry === "off" ? 30 : Number(retry), messages: Object.fromEntries(c.languages.map((l) => [l, messages[l]])) });
      onClose(true);
    } catch (err) {
      setMsg(err instanceof ApiError && err.details ? err.details.map((d) => `${d.field}: ${d.message}`).join(" · ") : (err as Error).message);
      setBusy(false);
    }
  }

  const editable = !!c && (c.status === "draft" || c.status === "scheduled");
  return (
    <div className="fade-in fixed inset-0 z-[60] grid place-items-center bg-ink/45 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(false); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="edit-title" className="dialog-in max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-lg border border-line bg-surface p-6 shadow-[0_20px_60px_rgba(17,17,19,.28)]">
        <h2 id="edit-title" className="text-base font-semibold text-ink">Edit campaign</h2>
        {loading && !c && <Loading />}
        {error && <ErrorState error={error} />}
        {c && !editable && <p className="mt-3 text-[13.5px] text-ink-2">Only draft or scheduled campaigns can be edited. This one is {c.status}.</p>}
        {c && editable && (
          <div className="mt-4 space-y-4">
            <Field label="Campaign name" error={errs.name}><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Max call attempts per participant" hint="Only failed, busy, unanswered or voicemail calls are retried.">
              <input type="number" min={1} max={5} className={inputCls} value={attempts} onChange={(e) => setAttempts(Math.min(5, Math.max(1, Math.round(Number(e.target.value)) || 1)))} />
            </Field>
            <Field label="If someone does not pick up or does not answer" hint="Called again automatically after this wait, until the attempts above are used up. Then a follow-up task is created.">
              <select className={inputCls} value={retry} onChange={(e) => setRetry(e.target.value)}>
                <option value="off">Do not retry automatically</option>
                {[5, 15, 30, 60, 120, 240].map((m) => <option key={m} value={m}>{m < 60 ? `Retry after ${m} minutes` : `Retry after ${m / 60} hour${m > 60 ? "s" : ""}`}</option>)}
              </select>
            </Field>
            {c.languages.map((l) => (
              <Field key={l} label={`Message: ${LANG_LABEL[l] ?? l}`} error={errs[`msg_${l}`]}>
                <textarea rows={5} lang={l} className={inputCls} value={messages[l] ?? ""} onChange={(e) => setMessages({ ...messages, [l]: e.target.value })} />
              </Field>
            ))}
            {msg && <p role="alert" className="text-[13px] font-medium text-bad">{msg}</p>}
          </div>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => onClose(false)} disabled={busy}>Cancel</Button>
          {editable && <Button onClick={() => void save()} disabled={busy}>{busy ? "Saving…" : "Save changes"}</Button>}
        </div>
      </div>
    </div>
  );
}
