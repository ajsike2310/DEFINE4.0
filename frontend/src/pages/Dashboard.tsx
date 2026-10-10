import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { Badge, Button, Card, Empty, ErrorState, Stat, StatGrid } from "../components/ui";
import { NoEvent } from "../components/NoEvent";
import { AttentionBand } from "../components/AttentionBand";
import { CAMPAIGN_LABEL, CAMPAIGN_TONE, pct } from "../services/labels";

/** Three questions, in order: who needs me, how many are coming, how are my campaigns doing.
 *  Everything analytical (outcome split, rates, languages, headcount detail) lives on the Analytics page. */
export default function Dashboard() {
  const { selected } = useEvent();
  const eid = selected?.id;
  const stats = useAsync(() => (eid ? api.analytics({ eventId: eid }) : Promise.resolve(null)), [eid]);
  const camps = useAsync(() => (eid ? api.campaignOverview(eid) : Promise.resolve(null)), [eid]);
  const queue = useAsync(() => (eid ? api.followupQueue({ eventId: eid }) : Promise.resolve([])), [eid]);
  const a = stats.data;
  const h = a?.headcount;
  const rows = camps.data?.campaigns.slice(0, 5) ?? [];
  const awaiting = a ? Math.max(a.totals.recipients - a.outcomes.confirmed - a.outcomes.declined - a.outcomes.opted_out, 0) : 0;

  return (
    <>
      <NoEvent />
      {selected && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h1 className="min-w-0 text-[clamp(20px,2.2vw,26px)] font-semibold leading-tight tracking-[-0.02em] [overflow-wrap:anywhere]">{selected.name}</h1>
            <Link to="/campaigns/new"><Button><Plus className="h-4 w-4" /> New campaign</Button></Link>
          </div>

          {a && (
            <StatGrid cols={4}>
              <Stat label="Total registered" value={a.totals.recipients} hint="Participants in this event's campaigns" to="/participants" />
              <Stat label="Accepted RSVP" value={a.outcomes.confirmed} hint={`${pct(a.rates.confirmation_rate)} of those who answered`} to="/participants" />
              <Stat label="Declined" value={a.outcomes.declined + a.outcomes.opted_out} hint={`${a.outcomes.opted_out} opted out`} to="/participants?filter=optout" />
              <Stat label="Awaiting answer" value={awaiting} hint="No clear yes or no yet" to="/followups" />
            </StatGrid>
          )}

          <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
            {queue.error ? <ErrorState title="Could not load the follow-up queue" error={queue.error} retry={queue.reload} />
              : <div className="reveal"><AttentionBand items={queue.data ?? []} /></div>}

            <section aria-label="Expected attendance" className="rounded-lg border border-line bg-surface p-5">
              <h2 className="text-[14px] font-semibold">Expected attending</h2>
              {stats.error ? <p className="mt-3 text-[13px] text-bad">Could not load the figures.</p> : h ? (<>
                <div className="mt-3 flex items-baseline gap-3 text-[clamp(40px,5vw,56px)] font-semibold leading-none tracking-[-0.03em] tabular-nums">
                  <span className="rounded-md bg-marigold px-2">{h.floor}</span><span className="text-[0.35em] font-medium text-muted">to</span><span>{h.ceiling}</span>
                </div>
                <p className="mt-2 text-[12.5px] text-muted">of {h.participants} participants · {pct(h.certainty)} certain</p>
                {a && <p className="mt-4 text-[13px] text-ink-2"><b className="font-semibold tabular-nums text-ink">{a.totals.recipients_contacted} of {a.totals.recipients}</b> reached</p>}
                {a && a.totals.simulated_calls > 0 && <div className="mt-3"><Badge tone="warn">Includes simulated calls</Badge></div>}
                <Link to="/analytics" className="mt-4 inline-block text-[13px] font-medium text-ink underline decoration-ink/30 hover:decoration-ink">Full analytics</Link>
              </>) : <p className="mt-3 text-[13px] text-muted">Appears once an attendance campaign has participants.</p>}
            </section>
          </div>

          <Card flush title="Campaigns" action={<Link className="text-xs font-medium text-ink underline decoration-ink/30 hover:decoration-ink" to="/campaigns">All campaigns</Link>}>
            {camps.error ? <div className="p-5"><ErrorState title="Could not load campaigns" error={camps.error} retry={camps.reload} /></div> : !rows.length
              ? <Empty title="No campaigns for this event" body="Create an attendance confirmation campaign to start." action={<Link to="/campaigns/new"><Button variant="secondary">New campaign</Button></Link>} />
              : (
                <ul className="divide-y divide-line-soft">
                  {rows.map((c) => (
                    <li key={c.campaign_id} className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-3">
                      <div className="min-w-0 flex-1 basis-56">
                        <Link className="text-[14px] font-semibold text-ink underline decoration-ink/30 hover:decoration-ink" to={`/campaigns/${c.campaign_id}`}>{c.name}</Link>
                        <p className={`mt-0.5 text-xs ${c.needs_attention || c.retry_eligible ? "font-medium text-signal" : "text-muted"}`}>{c.next_step}</p>
                      </div>
                      <div className="flex w-40 items-center gap-2" title={c.progress == null ? "No participants yet" : `${c.resolved} of ${c.participants} participants have a result`}>
                        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-line-soft"><span className="block h-full rounded-full bg-ink transition-[width] duration-700" style={{ width: `${(c.progress ?? 0) * 100}%` }} /></span>
                        <span className="w-9 text-right text-xs tabular-nums text-ink-2">{pct(c.progress)}</span>
                      </div>
                      <Badge tone={CAMPAIGN_TONE[c.status]}>{CAMPAIGN_LABEL[c.status] ?? c.status}</Badge>
                    </li>
                  ))}
                </ul>
              )}
          </Card>
        </div>
      )}
    </>
  );
}
