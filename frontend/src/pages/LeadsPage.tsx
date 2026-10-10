import { Fragment, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, Link2, Plus, Upload } from "lucide-react";
import { api, ApiError } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { useNotify } from "../hooks/useNotify";
import { Badge, Button, Card, Empty, ErrorState, Field, Loading, PageHeader, Segmented, Stat, StatGrid, Table, inputCls } from "../components/ui";
import { Meter } from "../components/Meter";
import { NoEvent } from "../components/NoEvent";
import { LANG_LABEL, OUTCOME_LABEL, OUTCOME_TONE, maskPhone, pct } from "../services/labels";
import type { Lead } from "../types";

export const SOURCE_LABEL: Record<string, string> = {
  registration_form: "Registration form", csv_import: "CSV import", manual: "Added by hand", referral: "Referral", walk_in: "Walk-in",
};
const STATUS: [string, string][] = [["", "All"], ["new", "New"], ["contacted", "Contacted"], ["qualified", "Qualified"], ["converted", "Converted"], ["lost", "Lost"]];

function Score({ n }: { n: number }) {
  return (
    <div className="flex items-center gap-2" title={`Contact readiness ${n} of 100`}>
      <span className="h-1.5 w-14 overflow-hidden rounded-[2px] bg-line-soft"><span className={`block h-full ${n >= 70 ? "bg-brand" : n >= 40 ? "bg-warn" : "bg-neutral/60"}`} style={{ width: `${n}%` }} /></span>
      <span className="w-7 text-xs tabular-nums text-ink-2">{n}</span>
    </div>
  );
}

function AddLead({ eventId, onDone }: { eventId: number; onDone: () => void }) {
  const { success, error: fail } = useNotify();
  const [f, setF] = useState({ name: "", phone: "", email: "", interest: "", language: "", source: "manual", consent: false });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: string | boolean) => setF((p) => ({ ...p, [k]: v }));
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true); setErrs({});
    try {
      await api.captureLead(eventId, { name: f.name.trim(), phone: f.phone, email: f.email || null, interest: f.interest || null,
        preferred_language: f.language || null, source: f.source, consent_status: f.consent ? "granted" : "unknown" });
      success("Lead added", f.consent ? undefined : "Consent is not recorded, so it cannot join a campaign that requires consent.");
      onDone();
    } catch (err) {
      if (err instanceof ApiError && err.details) setErrs(Object.fromEntries(err.details.map((d) => [d.field, d.message])));
      else fail("Could not add the lead", (err as Error).message);
    } finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit} className="panel-in mb-6 rounded-lg border border-line bg-surface p-5">
      <div className="grid gap-4 md:grid-cols-3">
        <Field label="Name" error={errs.name}><input className={inputCls} value={f.name} onChange={(e) => set("name", e.target.value)} required /></Field>
        <Field label="Phone number" error={errs.phone} hint="International format, e.g. +919876543210"><input className={inputCls} value={f.phone} onChange={(e) => set("phone", e.target.value)} required inputMode="tel" /></Field>
        <Field label="Email (optional)" error={errs.email}><input className={inputCls} type="email" value={f.email} onChange={(e) => set("email", e.target.value)} /></Field>
        <Field label="Interest (optional)"><input className={inputCls} value={f.interest} onChange={(e) => set("interest", e.target.value)} placeholder="e.g. AI, web, hardware" /></Field>
        <Field label="Language"><select className={inputCls} value={f.language} onChange={(e) => set("language", e.target.value)}><option value="">Not known</option><option value="en">English</option><option value="ml">Malayalam</option></select></Field>
        <Field label="Where did this lead come from?"><select className={inputCls} value={f.source} onChange={(e) => set("source", e.target.value)}>
          {Object.entries(SOURCE_LABEL).filter(([k]) => k !== "csv_import").map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
      </div>
      <label className="mt-4 flex items-start gap-2 text-[13px] text-ink-2">
        <input type="checkbox" checked={f.consent} onChange={(e) => set("consent", e.target.checked)} className="mt-0.5" />
        This person agreed to receive a call from the organisers about this event.
      </label>
      <div className="mt-4 flex gap-2"><Button disabled={busy}>{busy ? "Adding…" : "Add lead"}</Button><Button type="button" variant="ghost" onClick={onDone}>Cancel</Button></div>
    </form>
  );
}

export default function LeadsPage() {
  const { selected } = useEvent();
  const { success, error: fail, info, warn } = useNotify();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [target, setTarget] = useState("");
  const [consentOk, setConsentOk] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const eid = selected?.id;

  const leads = useAsync(() => (eid ? api.leads(eid, { status, q }) : Promise.resolve([] as Lead[])), [eid, status, q]);
  const summary = useAsync(() => (eid ? api.leadSummary(eid) : Promise.resolve(null)), [eid]);
  const camps = useAsync(() => (eid ? api.campaigns(eid) : Promise.resolve([])), [eid]);
  const open_camps = (camps.data ?? []).filter((c) => ["draft", "scheduled", "running"].includes(c.status));
  const refresh = () => { leads.reload(); summary.reload(); };

  const toggle = (id: number) => setPicked((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  async function convert() {
    if (!target || picked.size === 0) return;
    try {
      const r = await api.convertLeads(Number(target), [...picked]);
      const c = open_camps.find((x) => x.id === Number(target));
      if (r.converted) success(`${r.converted} lead${r.converted === 1 ? "" : "s"} added to the campaign`, c?.name, { action: { label: "Open campaign", to: `/campaigns/${target}` } });
      if (r.skipped.length) warn(`${r.skipped.length} skipped`, [...new Set(r.skipped.map((s) => s.reason))].join("; "));
      setPicked(new Set()); refresh();
    } catch (e) { fail("Could not convert the leads", (e as Error).message); }
  }

  async function onFile(file?: File) {
    if (!file || !eid) return;
    try {
      const r = await api.importLeads(eid, file, consentOk);
      if (r.imported) success(`${r.imported} lead${r.imported === 1 ? "" : "s"} imported`, r.rejected ? `${r.rejected} rows rejected (first: ${r.errors[0]?.error})` : undefined);
      else warn("No leads imported", r.errors[0] ? `Line ${r.errors[0].line}: ${r.errors[0].error}` : undefined);
      refresh();
    } catch (e) { fail("Import failed", (e as Error).message); }
    finally { if (fileRef.current) fileRef.current.value = ""; }
  }

  async function setLeadStatus(l: Lead, s: string) {
    try { await api.patchLead(l.id, { status: s }); refresh(); } catch (e) { fail("Could not update the lead", (e as Error).message); }
  }
  async function revoke(l: Lead) {
    try { await api.patchLead(l.id, { consent_status: "revoked" }); info("Consent withdrawn", `${l.name} will not be contacted.`); refresh(); }
    catch (e) { fail("Could not update the lead", (e as Error).message); }
  }

  async function loadSamples() {
    try { const r = await api.seedSampleLeads(); success(r.leads_added ? `${r.leads_added} sample leads loaded` : "Sample leads were already loaded", "Fictional people, clearly marked Sample."); refresh(); }
    catch (e) { fail("Could not load sample leads", (e as Error).message); }
  }

  async function copyLink() {
    if (!eid) return;
    const url = `${window.location.origin}/join/${eid}`;
    try { await navigator.clipboard.writeText(url); success("Sign-up link copied", url); }
    catch { info("Sign-up link", url, { duration: 0 }); }
  }

  const s = summary.data;
  return (
    <>
      <PageHeader title="Leads" subtitle="People interested in this event, captured with their consent. Convert them into a campaign when you are ready to call. Nothing is scraped or bought."
        actions={selected && (<>
          <Button variant="secondary" onClick={copyLink}><Link2 className="h-4 w-4" /> Copy sign-up link</Button>
          <Button variant="secondary" onClick={() => fileRef.current?.click()}><Upload className="h-4 w-4" /> Import CSV</Button>
          <Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Add lead</Button>
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" aria-label="Lead CSV file" onChange={(e) => onFile(e.target.files?.[0])} />
        </>)} />
      <NoEvent />
      {selected && (<>
        {adding && <AddLead eventId={selected.id} onDone={() => { setAdding(false); refresh(); }} />}
        <label className="mb-4 flex items-start gap-2 text-xs text-muted">
          <input type="checkbox" checked={consentOk} onChange={(e) => setConsentOk(e.target.checked)} className="mt-px" />
          <span>For CSV imports: I hold consent from everyone in the file. Leave unticked if not; those leads will show consent as not recorded.
            Columns: name, phone, email, interest, language.</span>
        </label>

        {summary.loading && !s && <Loading />}
        {summary.error && <ErrorState error={summary.error} retry={summary.reload} />}
        {s && (
          <div className="mb-6 space-y-6">
            <StatGrid cols={4}>
              <Stat label="Leads" value={s.total} hint={`${s.by_status.converted} converted to participants`} />
              <Stat label="Ready to convert" value={s.ready_to_convert} accent hint="Consent recorded, not yet converted" />
              <Stat label="Consent recorded" value={pct(s.consent_rate)} hint={s.total ? `${s.consented} of ${s.total} leads` : "No leads yet"} />
              <Stat label="Converted" value={pct(s.conversion_rate)} hint="Share of all leads now in a campaign" />
            </StatGrid>
            {s.total > 0 && (
              <div className="grid gap-6 lg:grid-cols-2">
                <Card title="Pipeline">
                  <div className="space-y-3.5">
                    {STATUS.slice(1).map(([k, l]) => <Meter key={k} label={l} value={s.total ? s.by_status[k] / s.total : null} tone={k === "lost" ? "bad" : "brand"} hint={`${s.by_status[k]} lead${s.by_status[k] === 1 ? "" : "s"}`} />)}
                  </div>
                </Card>
                <Card title="Where leads come from" flush>
                  <Table head={["Source", "Leads", "Consent", "Converted"]}>
                    {s.by_source.map((r) => (
                      <tr key={r.source}><td>{SOURCE_LABEL[r.source] ?? r.source}</td><td className="tabular-nums">{r.leads}</td>
                        <td className="tabular-nums">{r.consented}</td><td className="tabular-nums">{r.converted} <span className="text-xs text-muted">({pct(r.conversion_rate)})</span></td></tr>))}
                  </Table>
                </Card>
              </div>)}
          </div>)}

        <div className="mb-4 flex flex-wrap items-center gap-3">
          <Segmented label="Lead status" value={status} onChange={setStatus} options={STATUS} />
          <input aria-label="Search leads" className={`${inputCls} max-w-56`} placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>

        {picked.size > 0 && (
          <div role="region" aria-label="Convert selected leads" className="panel-in mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-brand/30 bg-brand-soft px-4 py-2.5 text-[13px]">
            <span className="font-medium text-ink">{picked.size} selected</span>
            <select aria-label="Target campaign" className={`${inputCls} max-w-64`} value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose a campaign…</option>
              {open_camps.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <Button disabled={!target} onClick={convert}>Add to campaign</Button>
            <Button variant="ghost" onClick={() => setPicked(new Set())}>Clear</Button>
            {open_camps.length === 0 && <span className="text-muted">Create a draft campaign first.</span>}
          </div>)}

        {leads.loading && !leads.data && <Loading />}
        {leads.error && <ErrorState error={leads.error} retry={leads.reload} />}
        {leads.data && (
          <Card flush>
            {leads.data.length === 0 ? (
              <Empty title={status || q ? "No leads match" : "No leads yet"} body={status || q ? "Try a different filter." : "Share the sign-up link, import a CSV of people who agreed to be contacted, or add one by hand."}
                action={!status && !q && (
                <div className="flex flex-wrap justify-center gap-2">
                  <Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Add lead</Button>
                  {selected.is_demo && <Button variant="secondary" onClick={loadSamples}>Load sample leads</Button>}
                </div>)} />
            ) : (
              <Table head={["", "Lead", "Phone", "Source", "Consent", "Readiness", "Status", ""]}>
                {leads.data.map((l) => (
                  <Fragment key={l.id}>
                    <tr>
                      <td className="w-8"><input type="checkbox" aria-label={`Select ${l.name}`} checked={picked.has(l.id)} disabled={l.status === "converted" || l.consent_status === "revoked"} onChange={() => toggle(l.id)} /></td>
                      <td><div className="font-medium text-ink">{l.name} {l.is_demo && <Badge tone="warn">Sample</Badge>}</div>
                        <div className="text-xs text-muted">{[l.email, l.interest, l.preferred_language && LANG_LABEL[l.preferred_language]].filter(Boolean).join(" · ") || "No details"}</div></td>
                      <td className="text-xs tabular-nums text-ink-2">{maskPhone(l.phone)}</td>
                      <td>{SOURCE_LABEL[l.source] ?? l.source}</td>
                      <td className="text-muted">{l.consent_status === "granted" ? "Granted" : l.consent_status === "revoked" ? "Withdrawn" : "Not recorded"}</td>
                      <td><Score n={l.score} /></td>
                      <td>{l.status === "converted"
                        ? <div className="flex flex-wrap items-center gap-1.5"><Badge tone="good">Converted</Badge>
                            {l.campaign_id && <Link className="text-xs text-ink underline decoration-ink/30 hover:decoration-ink" to={`/campaigns/${l.campaign_id}`}>campaign #{l.campaign_id}</Link>}
                            {l.recipient_outcome && l.recipient_outcome !== "pending" && <Badge tone={OUTCOME_TONE[l.recipient_outcome]}>{OUTCOME_LABEL[l.recipient_outcome]}</Badge>}</div>
                        : l.status === "lost" ? <Badge tone="bad">Lost</Badge>
                        : <select aria-label={`Status of ${l.name}`} className="rounded-md border border-line bg-surface px-1.5 py-1 text-xs" value={l.status} onChange={(e) => setLeadStatus(l, e.target.value)}>
                            {["new", "contacted", "qualified"].map((x) => <option key={x} value={x}>{x[0].toUpperCase() + x.slice(1)}</option>)}</select>}</td>
                      <td className="text-right"><button className="press inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-brand hover:bg-brand-soft" aria-expanded={open === l.id} onClick={() => setOpen(open === l.id ? null : l.id)}>
                        <ChevronRight className={`h-3.5 w-3.5 transition-transform duration-200 ${open === l.id ? "rotate-90" : ""}`} />Why {l.score}</button></td>
                    </tr>
                    {open === l.id && (
                      <tr><td colSpan={8} className="!bg-canvas/60 !px-6 !py-4">
                        <div className="expand-in flex flex-wrap items-start justify-between gap-6 text-[13px]">
                          <div><div className="mb-1.5 text-xs font-semibold text-muted">How this readiness score is made</div>
                            <ul className="space-y-0.5 text-ink-2">{l.score_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                            <p className="mt-2 max-w-md text-xs text-muted">A checklist of what we know about the lead. It does not predict whether they will attend or answer.</p></div>
                          <div className="space-y-2 text-ink-2">
                            {l.notes && <div>Note: {l.notes}</div>}
                            {l.consent_status !== "revoked" && l.status !== "lost" && <div><Button variant="danger" onClick={() => revoke(l)}>Withdraw consent</Button></div>}
                          </div>
                        </div>
                      </td></tr>)}
                  </Fragment>))}
              </Table>)}
          </Card>)}
      </>)}
    </>
  );
}
