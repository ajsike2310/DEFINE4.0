import { useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { api, ApiError } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { Button, Field, inputCls } from "../components/ui";

/** Public sign-up page for one event. No sidebar, no organiser data. Creates a lead with consent recorded
 *  only if the person ticks the box. Shared by link: /join/<event id>. */
export default function JoinPage() {
  const { eventId } = useParams();
  const id = Number(eventId);
  const ev = useAsync(() => api.event(id), [id]);
  const [f, setF] = useState({ name: "", phone: "", email: "", language: "", interest: "", consent: false });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: string | boolean) => setF((p) => ({ ...p, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true); setErrs({}); setMsg(null);
    try {
      await api.captureLead(id, { name: f.name.trim(), phone: f.phone, email: f.email || null, interest: f.interest || null,
        preferred_language: f.language || null, source: "registration_form", consent_status: "granted" });
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.code === "duplicate") setMsg("This number is already on the list. You do not need to sign up again.");
      else if (err instanceof ApiError && err.details) setErrs(Object.fromEntries(err.details.map((d) => [d.field, d.message])));
      else setMsg((err as Error).message);
    } finally { setBusy(false); }
  }

  return (
    <div className="min-h-screen bg-canvas px-4 py-10">
      <main className="mx-auto w-full max-w-lg">
        <div className="mb-6 text-[13px] font-semibold text-brand">Cadence</div>
        {ev.loading && !ev.data && <p role="status" className="text-muted">Loading…</p>}
        {ev.error && <div role="alert" className="rounded-lg border border-bad/30 bg-bad/6 p-4 text-sm text-bad">This sign-up link is not valid. Check it with the organisers.</div>}
        {ev.data && !done && (
          <form onSubmit={submit} className="rounded-lg border border-line bg-surface p-6">
            <h1 className="text-[22px] font-semibold leading-tight tracking-tight text-ink">{ev.data.name}</h1>
            <p className="mt-2 text-[13.5px] leading-relaxed text-muted">Leave your details and the organisers can call you about this event.</p>
            {ev.data.is_demo && <p className="mt-3 rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">This is a sample event. What you enter is demo data.</p>}
            <div className="mt-5 space-y-4">
              <Field label="Your name" error={errs.name}><input className={inputCls} value={f.name} onChange={(e) => set("name", e.target.value)} required autoComplete="name" /></Field>
              <Field label="Phone number" error={errs.phone} hint="With country code, for example +919876543210"><input className={inputCls} value={f.phone} onChange={(e) => set("phone", e.target.value)} required inputMode="tel" autoComplete="tel" /></Field>
              <Field label="Email (optional)" error={errs.email}><input className={inputCls} type="email" value={f.email} onChange={(e) => set("email", e.target.value)} autoComplete="email" /></Field>
              <Field label="Language for the call"><select className={inputCls} value={f.language} onChange={(e) => set("language", e.target.value)}>
                <option value="">No preference</option><option value="en">English</option><option value="ml">Malayalam</option></select></Field>
              <Field label="What are you interested in? (optional)"><input className={inputCls} value={f.interest} onChange={(e) => set("interest", e.target.value)} placeholder="e.g. AI, web, hardware" /></Field>
            </div>
            <label className="mt-5 flex items-start gap-2.5 text-[13px] leading-relaxed text-ink-2">
              <input type="checkbox" required checked={f.consent} onChange={(e) => set("consent", e.target.checked)} className="mt-1" />
              <span>I agree that the organisers of {ev.data.name} may phone me about this event. I can ask them to stop at any time, including by telling them during a call.</span>
            </label>
            {msg && <div role="alert" className="drop-in mt-4 rounded-md border border-bad/30 bg-bad/8 px-3 py-2 text-[13px] text-bad">{msg}</div>}
            <Button className="mt-5 w-full justify-center" disabled={busy || !f.consent}>{busy ? "Sending…" : "Sign up"}</Button>
          </form>
        )}
        {done && (
          <div role="status" className="panel-in rounded-lg border border-good/30 bg-surface p-6">
            <CheckCircle2 className="h-6 w-6 text-good" aria-hidden />
            <h1 className="mt-3 text-[20px] font-semibold text-ink">You are on the list</h1>
            <p className="mt-2 text-[13.5px] leading-relaxed text-muted">The organisers may call you about {ev.data?.name}. If you change your mind, tell them or say so on the call.</p>
          </div>
        )}
      </main>
    </div>
  );
}
