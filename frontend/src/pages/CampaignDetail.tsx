import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify, type NotifyTone } from "../hooks/useNotify";
import { Badge, Button, Card, Empty, ErrorState, Field, Loading, PageHeader, SimBadge, Stat, StatGrid, Table, inputCls } from "../components/ui";
import { CALL_LABEL, CALL_TONE, LANG_LABEL, OUTCOME_LABEL, OUTCOME_TONE, PURPOSE_LABEL, fmtDate, maskPhone, pct } from "../services/labels";
import { CAMPAIGN_TONE } from "./Campaigns";
import { ImportRecipients } from "../components/ImportRecipients";

export default function CampaignDetail() {
  const id = Number(useParams().id);
  const camp = useAsync(() => api.campaign(id), [id]);
  const recs = useAsync(() => api.recipients(id), [id]);
  const atts = useAsync(() => api.attempts(id), [id]);
  const ints = useAsync(() => api.intents(id), [id]);
  const fus = useAsync(() => api.followups({ campaignId: id }), [id]);
  const stats = useAsync(() => api.analytics({ campaignId: id }), [id]);
  const { notify, success, error: fail, confirm } = useNotify();
  // the wizard leaves a one-off summary of what it just did (participants imported, calls placed)
  useEffect(() => {
    try {
      const m = sessionStorage.getItem(`note-${id}`);
      if (m) { sessionStorage.removeItem(`note-${id}`); success("Campaign created", m); }
    } catch { /* storage unavailable */ }
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "", lang: "", consent: false });
  const [formErr, setFormErr] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  const reloadAll = () => { camp.reload(); recs.reload(); atts.reload(); ints.reload(); fus.reload(); stats.reload(); };
  type Outcome = { title: string; message?: string; tone?: NotifyTone };
  async function act(fn: () => Promise<unknown>, ok: (r: never) => Outcome) {
    setBusy(true);
    try { const o = ok((await fn()) as never); notify({ tone: o.tone ?? "success", title: o.title, message: o.message }); }
    catch (e) { fail("That did not work", (e as Error).message); }
    setBusy(false); reloadAll();
  }
  async function cancelCampaign() {
    const yes = await confirm({ title: "Cancel this campaign?", message: "No further calls will be placed. Results so far are kept.", confirmLabel: "Cancel campaign", cancelLabel: "Keep it", danger: true });
    if (yes) void act(() => api.cancelCampaign(id), () => ({ title: "Campaign cancelled", tone: "info" }));
  }
  async function recordOptOut(rid: number, name: string) {
    const yes = await confirm({ title: `Record opt-out for ${name}?`, message: "They will not be called again and their open follow-ups are cancelled.", confirmLabel: "Record opt-out", danger: true });
    if (yes) void act(() => api.optOut(rid), () => ({ title: `${name} opted out`, message: "No further calls or follow-ups for this participant.", tone: "info" }));
  }
  async function addRecipient(e: React.FormEvent) {
    e.preventDefault(); setFormErr(null);
    try {
      await api.addRecipient(id, { name: form.name, phone: form.phone, preferred_language: form.lang || null, consent_status: form.consent ? "granted" : "unknown" });
      setForm({ name: "", phone: "", lang: "", consent: false }); reloadAll();
      success("Participant added", form.consent ? undefined : "Consent is unknown, so they will be skipped at launch.", { duration: 4000 });
    } catch (err) { setFormErr((err as Error).message); }
  }

  if (camp.loading && !camp.data) return <Loading />;
  if (camp.error) return <ErrorState error={camp.error} retry={camp.reload} />;
  const c = camp.data!;
  const recName = new Map((recs.data ?? []).map((r) => [r.id, r]));
  const canEdit = ["draft", "scheduled", "running"].includes(c.status);

  return (
    <>
      <PageHeader title={c.name} subtitle={`${PURPOSE_LABEL[c.purpose] ?? c.purpose}, ${c.languages.map((l) => LANG_LABEL[l]).join(" and ")}, up to ${c.max_attempts} attempts`}
        actions={<>
          {(c.status === "draft" || c.status === "scheduled") && <Button disabled={busy || c.recipient_count === 0} title={c.recipient_count === 0 ? "Add recipients first" : undefined}
            onClick={() => act(() => api.startCampaign(id), (r: { dispatched: number; skipped: unknown[] }) => ({ title: r.dispatched ? "Campaign started" : "No calls were placed", tone: r.dispatched ? "success" : "warn", message: `${r.dispatched} call${r.dispatched === 1 ? "" : "s"} placed; ${r.skipped.length} skipped (no consent, opted out, or already resolved).` }))}>Start campaign</Button>}
          {c.purpose === "attendance_confirmation" && ["running", "completed"].includes(c.status) && (recs.data ?? []).some((r) => r.outcome === "unclear" && !r.opted_out) &&
            <Button variant="secondary" disabled={busy} title="One short yes/no call to each person whose answer was unclear (once each)"
              onClick={() => act(() => api.clarifyCampaign(id), (r: { dispatched: number; skipped: unknown[] }) => ({ title: r.dispatched ? "Clarification calls placed" : "Nobody to clarify", tone: r.dispatched ? "success" : "warn", message: `${r.dispatched} placed; ${r.skipped.length} not eligible (already asked, opted out, or no consent).` }))}>Clarify unclear answers</Button>}
          {c.status === "running" && <Button variant="secondary" disabled={busy} onClick={() => act(() => api.retryDue(id, c.is_demo), (r: { dispatched: number }) => ({ title: r.dispatched ? "Retries placed" : "No retries due", tone: r.dispatched ? "success" : "info", message: `${r.dispatched} retry call${r.dispatched === 1 ? "" : "s"} placed.` }))}>{c.is_demo ? "Run retries now" : "Run due retries"}</Button>}
          {["draft", "scheduled", "running"].includes(c.status) && <Button variant="danger" disabled={busy} onClick={cancelCampaign}>Cancel</Button>}
        </>} />
      <div className="mb-4 flex gap-2"><Badge tone={CAMPAIGN_TONE[c.status]}>{c.status}</Badge>{c.is_demo && <Badge tone="warn">Simulated demo data — no real calls are placed</Badge>}</div>

      {stats.data && (
        <div className="mb-6"><StatGrid cols={5}>
          <Stat label="Recipients" value={stats.data.totals.recipients} />
          <Stat label="Calls attempted" value={stats.data.totals.calls_attempted} />
          <Stat label="Answer rate" value={pct(stats.data.rates.answer_rate)} hint="answered / finished calls" />
          <Stat label="Completion" value={pct(stats.data.rates.completion_rate)} hint="recipients with a final outcome" />
          <Stat label="Confirmed" value={stats.data.outcomes.confirmed} hint={`of ${stats.data.totals.recipients_responded} who responded`} />
        </StatGrid></div>
      )}

      <div className="space-y-6">
        <Card flush title={`Recipients (${recs.data?.length ?? 0})`}
          action={canEdit && <Button variant="secondary" aria-expanded={importing} onClick={() => setImporting(!importing)}>Import from CSV</Button>}>
          {canEdit && importing && <ImportRecipients campaignId={id} onDone={(r) => {
            reloadAll();
            if (r.imported > 0) success(`${r.imported} participant${r.imported === 1 ? "" : "s"} imported`, r.rejected ? `${r.rejected} rows were rejected.` : undefined, { duration: 4000 });
          }} />}
          {canEdit && (
            <form onSubmit={addRecipient} className="grid gap-3 border-b border-line-soft p-5 md:grid-cols-[1fr_1fr_8rem_auto_auto] md:items-end">
              <Field label="Name"><input required className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
              <Field label="Phone (E.164)"><input required placeholder="+919876543210" className={inputCls} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
              <Field label="Language"><select className={inputCls} value={form.lang} onChange={(e) => setForm({ ...form, lang: e.target.value })}><option value="">Default</option>{c.languages.map((l) => <option key={l} value={l}>{LANG_LABEL[l]}</option>)}</select></Field>
              <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={form.consent} onChange={(e) => setForm({ ...form, consent: e.target.checked })} />Has consent</label>
              <Button type="submit">Add</Button>
            </form>
          )}
          {formErr && <p role="alert" className="drop-in px-5 pt-3 text-sm font-medium text-bad">{formErr}</p>}
          {recs.error ? <ErrorState error={recs.error} retry={recs.reload} /> : !recs.data?.length ? <Empty title="No recipients" body="Add recipients above to enable starting this campaign." /> : (
            <Table head={["Name", "Phone", "Language", "Consent", "Outcome", ""]}>
              {recs.data.map((r) => (
                <tr key={r.id}>
                  <td>{r.name}{r.external_ref && <span className="ml-1 text-xs text-muted">{r.external_ref}</span>}</td>
                  <td className="tabular-nums">{maskPhone(r.phone)}</td>
                  <td>{r.preferred_language ? LANG_LABEL[r.preferred_language] : "Default"}</td>
                  <td>{r.consent_status}</td>
                  <td><Badge tone={OUTCOME_TONE[r.outcome]}>{OUTCOME_LABEL[r.outcome]}</Badge></td>
                  <td className="text-right">{!r.opted_out && <button className="press rounded px-1.5 py-0.5 text-xs text-bad hover:bg-bad/8" onClick={() => recordOptOut(r.id, r.name)}>Record opt-out</button>}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card flush title="Call attempts & classified responses">
          {!atts.data?.length ? <Empty title="No calls yet" body="Start the campaign to place calls." /> : (
            <Table head={["Recipient", "Attempt", "Call status", "Source", "Response intent", "Evidence", "Next action"]}>
              {atts.data.map((a) => {
                const it = ints.data?.find((i) => i.call_attempt_id === a.id);
                return (
                  <tr key={a.id}>
                    <td className="whitespace-nowrap">{recName.get(a.recipient_id)?.name ?? a.recipient_id}</td>
                    <td>#{a.attempt_number} {a.mode === "clarify" && <Badge tone="info">Clarification</Badge>}</td>
                    <td><Badge tone={CALL_TONE[a.status]}>{CALL_LABEL[a.status]}</Badge>{a.next_retry_at && <div className="text-xs text-muted">retry after {fmtDate(a.next_retry_at)}</div>}</td>
                    <td><SimBadge simulated={a.is_simulated} /></td>
                    <td className="whitespace-nowrap">{it ? <>{it.intent.replace(/_/g, " ")} {it.needs_review && <Badge tone="warn">review</Badge>}</> : "—"}</td>
                    <td className="text-xs text-muted">{it ? `${it.method}${it.evidence ? `: ${it.evidence}` : ""}${it.notes.length ? ` (${it.notes.join("; ")})` : ""}` : ""}</td>
                    <td className="whitespace-nowrap text-xs">{it?.next_action.replace(/_/g, " ") ?? ""}</td>
                  </tr>
                );
              })}
            </Table>
          )}
          <p className="mt-3 text-xs text-muted">Intent score is an internal heuristic, not a probability. Unclear responses are never counted as confirmation.</p>
        </Card>

        <Card flush title="Follow-ups">
          {!fus.data?.length ? <Empty title="No follow-ups" body="Callback requests, info requests and unclear responses create follow-ups here." /> : (
            <Table head={["Recipient", "Action", "Status", "When", "Note", ""]}>
              {fus.data.map((f) => (
                <tr key={f.id}>
                  <td>{recName.get(f.recipient_id)?.name ?? f.recipient_id}</td>
                  <td>{f.action_type.replace(/_/g, " ")}</td>
                  <td><Badge tone={f.status === "completed" ? "good" : f.status === "cancelled" ? "neutral" : "warn"}>{f.status}</Badge></td>
                  <td>{f.scheduled_at ? fmtDate(f.scheduled_at) : "time not set"}</td>
                  <td className="text-xs text-muted">{f.note}</td>
                  <td className="text-right">{(f.status === "pending" || f.status === "scheduled") &&
                    <button className="text-xs underline" onClick={() => act(() => api.patchFollowup(f.id, { status: "completed" }), () => ({ title: "Follow-up completed" }))}>Mark complete</button>}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>
    </>
  );
}
