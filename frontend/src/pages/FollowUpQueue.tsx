import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, Eye, EyeOff, Phone } from "lucide-react";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { useNotify } from "../hooks/useNotify";
import { Badge, Button, Empty, ErrorState, Loading, PageHeader } from "../components/ui";
import { NoEvent } from "../components/NoEvent";
import { OUTCOME_LABEL, fmtDate, maskPhone } from "../services/labels";

const PRIO: Record<number, { label: string; tone: "bad" | "warn" | "info"; rail: string }> = {
  1: { label: "P1 Due now", tone: "bad", rail: "bg-bad" },
  2: { label: "P2 Needs a person", tone: "warn", rail: "bg-warn" },
  3: { label: "P3 Info to relay", tone: "info", rail: "bg-info" },
};

export default function FollowUpQueue() {
  const { selected } = useEvent();
  const { data, error, loading, reload } = useAsync(() => (selected ? api.followupQueue({ eventId: selected.id }) : Promise.resolve([])), [selected?.id]);
  const { success, warn, error: fail, info } = useNotify();
  const [leaving, setLeaving] = useState<number | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [shown, setShown] = useState<Set<number>>(new Set());   // numbers revealed in full; masked by default
  const toggleNumber = (id: number) => setShown((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  async function clarify(rid: number) {
    try {
      const r = await api.clarifyRecipient(rid);
      if (r.dispatched) success("Clarification call placed", "The answer updates this queue when the call finishes.");
      else warn("Clarification call not placed", r.skipped[0]?.reason ?? "Not allowed for this participant.");
      reload();
    } catch (e) { fail("Could not place the call", (e as Error).message); }
  }
  async function setStatus(id: number, status: string) {
    try {
      await api.patchFollowup(id, { status });
      if (status === "completed") success("Follow-up completed"); else info("Follow-up dismissed");
      setLeaving(id);                              // let the row animate out before it leaves the list
      setTimeout(() => { setLeaving(null); reload(); }, 330);
    } catch (e) { fail("Could not update the follow-up", (e as Error).message); }
  }
  return (
    <>
      <PageHeader title="Follow-up queue" subtitle="Open tasks created from participant responses, ordered by fixed rules: due callbacks first, then responses a person must resolve, then information to relay." />
      <NoEvent />
      {selected && (<>
        {loading && !data && <Loading />}
        {error && <ErrorState error={error} retry={reload} />}
        {data && (data.length === 0
          ? <div className="rounded-lg border border-line bg-surface"><Empty title="Nothing to follow up" body="Callback requests, unclear answers and information requests will appear here after calls complete." /></div>
          : <ul className="space-y-3">
            {data.map((i) => {
              const p = PRIO[i.priority] ?? PRIO[3];
              return (
                <li key={i.followup_id} className={leaving === i.followup_id ? "row-leave" : ""}>
                  <article className="rounded-lg border border-line bg-surface">
                    <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 px-5 py-4">
                      <div className="min-w-0 flex-1 basis-80">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[15px] font-semibold text-ink">{i.participant_name}</span>
                          <Badge tone={p.tone}>{p.label}</Badge>
                          {i.is_simulated && <Badge tone="warn">Simulated</Badge>}
                        </div>
                        {i.participant_phone && (
                          <p className="mt-1 flex items-center gap-1.5 text-[13px] text-ink-2">
                            <Phone aria-hidden className="h-3.5 w-3.5 text-muted" />
                            <span className="tabular-nums">{shown.has(i.followup_id) ? i.participant_phone : maskPhone(i.participant_phone)}</span>
                            <button type="button" onClick={() => toggleNumber(i.followup_id)} aria-pressed={shown.has(i.followup_id)}
                              aria-label={`${shown.has(i.followup_id) ? "Hide" : "Show"} full number for ${i.participant_name}`}
                              className="press grid h-6 w-6 place-items-center rounded-md text-muted hover:bg-canvas hover:text-ink">
                              {shown.has(i.followup_id) ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                            </button>
                          </p>
                        )}
                        <p className="mt-1.5 text-[13.5px] text-ink-2">{i.reason}</p>
                        <p className="mt-1 text-[13.5px] text-ink"><span className="font-semibold">Next:</span> {i.recommended_action}</p>
                        {i.scheduled_at && <p className="mt-1 text-xs font-medium text-ink-2">Due {fmtDate(i.scheduled_at)}</p>}
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Button onClick={() => setStatus(i.followup_id, "completed")}>Mark complete</Button>
                        {i.can_clarify && !i.clarification_attempted && <Button variant="secondary" onClick={() => clarify(i.recipient_id)} title="One short yes/no call, once only">Clarify call</Button>}
                        <Button variant="ghost" onClick={() => setStatus(i.followup_id, "cancelled")}>Dismiss</Button>
                      </div>
                    </div>
                    <div className="border-t border-line-soft px-5 py-2">
                      <button type="button" aria-expanded={open === i.followup_id} onClick={() => setOpen(open === i.followup_id ? null : i.followup_id)}
                        className="press inline-flex items-center gap-1 text-xs font-medium text-muted hover:text-ink">
                        <ChevronDown aria-hidden className={`h-3.5 w-3.5 transition-transform ${open === i.followup_id ? "rotate-180" : ""}`} />Details
                      </button>
                      {open === i.followup_id && (
                        <dl className="expand-in mt-2 grid gap-x-6 gap-y-1.5 pb-2 text-[12.5px] sm:grid-cols-[8rem_minmax(0,1fr)]">
                          <dt className="text-muted">Campaign</dt><dd><Link className="text-ink underline decoration-ink/30 hover:decoration-ink" to={`/campaigns/${i.campaign_id}`}>{i.campaign_name}</Link></dd>
                          {i.participant_ref && <><dt className="text-muted">Participant ID</dt><dd>{i.participant_ref}</dd></>}
                          <dt className="text-muted">Latest outcome</dt><dd>{OUTCOME_LABEL[i.latest_outcome] ?? i.latest_outcome}</dd>
                          <dt className="text-muted">Why this priority</dt><dd>{i.priority_reason}</dd>
                          {i.note && <><dt className="text-muted">What was said</dt><dd>{i.note}</dd></>}
                          {i.clarification_attempted && <><dt className="text-muted">Clarification</dt><dd>Already tried once</dd></>}
                          <dt className="text-muted">Status</dt><dd>{i.status}{i.scheduled_at ? "" : ", no time set"}</dd>
                        </dl>
                      )}
                    </div>
                  </article>
                </li>
              );
            })}
          </ul>)}
      </>)}
    </>
  );
}
