import { useState } from "react";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { useMounted } from "../hooks/useCountUp";
import { Badge, Card, ErrorState, Loading, Segmented, Stat, StatGrid, Table } from "../components/ui";
import { OutcomeByLanguage } from "../components/OutcomeChart";
import { ResponsesChart } from "../components/ResponsesChart";
import { OUTCOME_LABEL, pct } from "../services/labels";

const DEFS: [string, string, string][] = [
  ["answer_rate", "Answer rate", "calls answered ÷ calls that reached a final status"],
  ["failure_rate", "Failure rate", "failed/busy/no-answer/voicemail calls ÷ finished calls"],
  ["completion_rate", "Completion rate", "participants with a final outcome ÷ all participants"],
  ["confirmation_rate", "Attendance confirmation rate", "participants who said they will attend ÷ participants who gave a classified response"],
  ["decline_rate", "Decline rate", "declined ÷ participants who gave a classified response"],
  ["unclear_rate", "Unclear rate", "unclear + needs-human ÷ participants who gave a classified response"],
];

/** Questions an organiser asks, in order: how many are coming, what did people say, how did the calls go, and does it
 *  differ by language. Definitions are one click away at the bottom. */
export default function AnalyticsPage() {
  const [source, setSource] = useState("all");
  const { selected } = useEvent();
  const mounted = useMounted();
  const { data: a, error, loading, reload } = useAsync(() => api.analytics({ source, eventId: selected?.id }), [source, selected?.id]);
  const h = a?.headcount;
  const mixed = !!a && source === "all" && a.totals.simulated_calls > 0;
  const w = (n: number) => (mounted && h ? `${(n / h.participants) * 100}%` : "0%");
  const seg = "h-full transition-[width] duration-[900ms] ease-[var(--ease-out-soft)]";

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[24px] font-semibold leading-tight tracking-[-0.02em]">Analytics</h1>
          <p className="mt-1 text-[13.5px] text-muted">{selected ? selected.name : "Select an event"}</p>
        </div>
        <Segmented label="Data source" value={source} onChange={setSource} options={[["all", "All calls"], ["real", "Real"], ["simulated", "Simulated"]]} />
      </div>
      {loading && !a && <Loading />}
      {error && <ErrorState error={error} retry={reload} />}
      {a && (
        <div className="space-y-6">
          <StatGrid cols={4}>
            <Stat label="Registered" value={a.totals.recipients} hint={`${a.totals.recipients_contacted} reached`} />
            <Stat label="Accepted RSVP" value={a.outcomes.confirmed} hint={`${pct(a.rates.confirmation_rate)} of those who answered`} />
            <Stat label="Answer rate" value={pct(a.rates.answer_rate)} hint={`${a.totals.calls_answered} of ${a.totals.calls_attempted} calls answered`} />
            <Stat label="Needs a person" value={a.outcomes.unclear + a.outcomes.human_required} accent={a.outcomes.unclear + a.outcomes.human_required > 0} to="/followups" hint="Unclear or flagged answers" />
          </StatGrid>

          <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Card title="Responses">
              <ResponsesChart outcomes={a.outcomes} total={a.totals.recipients} />
            </Card>

            <Card title="Expected attending" action={mixed ? <Badge tone="warn">Includes simulated</Badge> : undefined}>
              {h ? (<>
                <div className="flex items-baseline gap-2.5 text-[44px] font-semibold leading-none tracking-[-0.03em] tabular-nums">
                  <span className="rounded-md bg-marigold px-1.5">{h.floor}</span><span className="text-[16px] font-medium text-muted">to</span><span>{h.ceiling}</span>
                </div>
                <p className="mt-2 text-[12.5px] text-muted">of {h.participants} participants · {pct(h.certainty)} certain</p>
                <div className="mt-4 flex h-2.5 overflow-hidden rounded-full bg-line-soft" role="img" aria-label={`${h.confirmed} confirmed, ${h.unknown} not yet certain, ${h.declined} declined`}>
                  <div className={`${seg} bg-good`} style={{ width: w(h.confirmed) }} />
                  <div className={`${seg} hatch`} style={{ width: w(h.unknown) }} />
                  <div className={`${seg} bg-bad/60`} style={{ width: w(h.declined) }} />
                </div>
                <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
                  <span className="inline-flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-good" />Confirmed <b className="font-semibold text-ink">{h.confirmed}</b></span>
                  <span className="inline-flex items-center gap-1.5"><i className="hatch h-2 w-2 rounded-full" />Not yet certain <b className="font-semibold text-ink">{h.unknown}</b></span>
                  <span className="inline-flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-bad/60" />Declined <b className="font-semibold text-ink">{h.declined}</b></span>
                </div>
                {h.unknown > 0 && (
                  <p className="mt-4 border-t border-line-soft pt-3 text-[12.5px] leading-relaxed text-ink-2">
                    <span className="font-semibold text-signal">To narrow it:</span> {Object.entries(h.unknown_breakdown).map(([k, n]) => `${n} ${k === "opted_out" ? "opted out" : (OUTCOME_LABEL[k] ?? k).toLowerCase()}`).join(", ")}.
                  </p>
                )}
              </>) : <p className="text-[13px] text-muted">Appears once an attendance campaign has participants.</p>}
            </Card>
          </div>

          {a.by_language.length > 0 && (
            <Card title="By language"><OutcomeByLanguage rows={a.by_language} /></Card>
          )}

          <StatGrid label="Calls" cols={4}>
            <Stat label="Attempted" value={a.totals.calls_attempted} hint={`${a.totals.simulated_calls} simulated, ${a.totals.real_calls} real`} />
            <Stat label="Answered" value={a.totals.calls_answered} />
            <Stat label="Failed or unanswered" value={a.totals.failed_or_unanswered} />
            <Stat label="Retries" value={a.totals.retries} />
          </StatGrid>

          <details className="rounded-lg border border-line bg-surface">
            <summary className="cursor-pointer px-5 py-3 text-[13px] font-medium text-ink">How the figures are calculated</summary>
            <div className="border-t border-line-soft">
              <p className="px-5 pt-3 text-xs leading-relaxed text-muted">A dash means the denominator is zero (undefined), not 0%. “Attending” means the participant said so on a call; Cadence does not record actual check-in, so this is stated intent, not verified attendance.</p>
              <Table head={["Metric", "Value", "Definition"]}>
                {DEFS.map(([k, label, def]) => <tr key={k}><td className="font-medium">{label}</td><td className="tabular-nums">{pct(a.rates[k])}</td><td className="text-muted">{def}</td></tr>)}
              </Table>
            </div>
          </details>
        </div>
      )}
    </>
  );
}
