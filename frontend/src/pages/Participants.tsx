import { Fragment, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AudioLines, ChevronRight, Phone } from "lucide-react";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { Badge, Card, Empty, ErrorState, Loading, PageHeader, Segmented, SimBadge, Table } from "../components/ui";
import { NoEvent } from "../components/NoEvent";
import { BrowserCallDialog } from "../components/BrowserCall";
import { LiveCallDialog } from "../components/LiveCall";
import { CALL_LABEL, CALL_TONE, LANG_LABEL, OUTCOME_LABEL, OUTCOME_TONE, fmtDate, maskPhone } from "../services/labels";

const FILTERS: [string, string][] = [["all", "All"], ["attention", "Unresolved"], ["callback", "Callback requested"], ["retry", "Retry eligible"], ["optout", "Opted out"]];

function History({ rid }: { rid: number }) {
  const { data, error, loading } = useAsync(() => api.history(rid), [rid]);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error ?? new Error("No data")} />;
  return (
    <div className="expand-in grid gap-6 text-[13px] md:grid-cols-2">
      <div><div className="mb-2 text-xs font-semibold text-muted">Calls</div>
        {data.attempts.length === 0 ? <span className="text-muted">No calls yet.</span> : (
          <ol className="relative space-y-3 border-l border-line pl-4">
            {data.attempts.map((a) => {
              const it = data.intents.find((i) => i.call_attempt_id === a.id);
              return <li key={a.id} className="relative">
                <i aria-hidden className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-canvas bg-brand" />
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-muted">#{a.attempt_number}</span>{a.mode === "clarify" && <Badge tone="info">Clarification</Badge>}
                  <Badge tone={CALL_TONE[a.status]}>{CALL_LABEL[a.status]}</Badge><SimBadge simulated={a.is_simulated} />
                  <span className="text-xs text-muted">{fmtDate(a.started_at)}</span>
                </div>
                {it && <div className="mt-1 text-ink-2">→ <strong className="font-medium">{it.intent.replace(/_/g, " ")}</strong> <span className="text-xs text-muted">({it.method}{it.evidence ? `: ${it.evidence}` : ""})</span></div>}
              </li>;
            })}
          </ol>)}</div>
      <div><div className="mb-2 text-xs font-semibold text-muted">Follow-ups</div>
        {data.followups.length === 0 ? <span className="text-muted">None.</span> : data.followups.map((f) => (
          <div key={f.id} className="mb-2">{f.action_type.replace(/_/g, " ")} · <Badge tone={f.status === "completed" ? "good" : "warn"}>{f.status}</Badge> <span className="text-muted">{f.note}</span></div>))}</div>
    </div>
  );
}

export default function ParticipantsPage() {
  const { selected } = useEvent();
  const [params] = useSearchParams();
  const initial = params.get("filter") ?? "all";
  const [filter, setFilter] = useState(FILTERS.some(([k]) => k === initial) ? initial : "all");
  const [open, setOpen] = useState<number | null>(null);
  const [calling, setCalling] = useState<{ cid: number; rid: number; name: string; mode: "main" | "clarify"; live: boolean } | null>(null);
  const { data, error, loading, reload } = useAsync(() => (selected ? api.participants({ eventId: selected.id, filter: filter === "all" ? "" : filter }) : Promise.resolve([])), [selected?.id, filter]);
  return (
    <>
      <PageHeader title="Participants" subtitle="Participants of the selected event across its campaigns. Phone numbers are masked here." />
      <NoEvent />
      {selected && (<>
        <div className="mb-4"><Segmented label="Filter" value={filter} onChange={setFilter} options={FILTERS as [string, string][]} /></div>
        {loading && !data && <Loading />}
        {error && <ErrorState error={error} retry={reload} />}
        {data && <Card flush>{data.length === 0 ? <Empty title="No participants match" body="Add participants from a campaign page or import a CSV in the campaign wizard." /> : (
          <Table head={["Participant", "Phone", "Language", "Campaign", "Consent", "Latest outcome", ""]}>
            {data.map((r) => (
              <Fragment key={r.id}>
                <tr className="cursor-pointer" onClick={() => setOpen(open === r.id ? null : r.id)}>
                  <td>{r.name}{r.external_ref && <span className="ml-2 text-xs text-muted">{r.external_ref}</span>} {r.is_demo && <Badge tone="warn">Sample</Badge>}</td>
                  <td className="text-xs tabular-nums text-ink-2">{maskPhone(r.phone)}</td>
                  <td>{r.preferred_language ? LANG_LABEL[r.preferred_language] : "Default"}</td>
                  <td><Link className="text-xs text-ink underline decoration-ink/30 hover:decoration-ink" to={`/campaigns/${r.campaign_id}`} onClick={(e) => e.stopPropagation()}>#{r.campaign_id}</Link></td>
                  <td className="text-muted">{r.consent_status}{r.opted_out && " · opted out"}</td>
                  <td><Badge tone={OUTCOME_TONE[r.outcome]}>{OUTCOME_LABEL[r.outcome]}</Badge></td>
                  <td className="whitespace-nowrap text-right">
                    {r.is_demo && <>
                      <button className="press mr-1 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-brand hover:bg-brand-soft" title="Hands-free browser demo: you talk, the agent answers"
                        onClick={(e) => { e.stopPropagation(); setCalling({ cid: r.campaign_id, rid: r.id, name: r.name, mode: r.outcome === "unclear" ? "clarify" : "main", live: true }); }}>
                        <AudioLines className="h-3.5 w-3.5" aria-hidden />Live call</button>
                      <button className="press mr-1 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-brand hover:bg-brand-soft" title="Browser demo with keys and text: you play the participant"
                        onClick={(e) => { e.stopPropagation(); setCalling({ cid: r.campaign_id, rid: r.id, name: r.name, mode: r.outcome === "unclear" ? "clarify" : "main", live: false }); }}>
                        <Phone className="h-3.5 w-3.5" aria-hidden />Manual call</button></>}
                    <button className="press inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-brand hover:bg-brand-soft" aria-expanded={open === r.id}
                    onClick={(e) => { e.stopPropagation(); setOpen(open === r.id ? null : r.id); }}>
                    <ChevronRight className={`h-3.5 w-3.5 transition-transform duration-200 ${open === r.id ? "rotate-90" : ""}`} />{open === r.id ? "Hide" : "History"}</button></td>
                </tr>
                {open === r.id && <tr><td colSpan={7} className="!bg-canvas/60 !px-6 !py-4"><History rid={r.id} /></td></tr>}
              </Fragment>
            ))}
          </Table>)}</Card>}
      </>)}
      {calling && (calling.live
        ? <LiveCallDialog campaignId={calling.cid} recipientId={calling.rid} name={calling.name} mode={calling.mode} onClose={(changed) => { setCalling(null); if (changed) reload(); }} />
        : <BrowserCallDialog campaignId={calling.cid} recipientId={calling.rid} name={calling.name} mode={calling.mode} onClose={(changed) => { setCalling(null); if (changed) reload(); }} />)}
    </>
  );
}
