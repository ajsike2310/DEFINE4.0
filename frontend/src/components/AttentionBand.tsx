import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import type { QueueItem } from "../types";
import { Badge, Button } from "./ui";

/** The page's reason to exist: who needs a person and what to do. Most urgent first. Only name, priority and the
 *  next step are shown here; the full detail lives in the follow-up queue. Wrapped, never truncated (Malayalam). */
export function AttentionBand({ items }: { items: QueueItem[] }) {
  const top = items.slice(0, 3);
  const more = items.length - top.length;
  return (
    <section aria-labelledby="needs-attention" className="min-w-0 overflow-hidden rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-signal/20 bg-signal-soft/60 px-5 py-3">
        <h2 id="needs-attention" className="flex items-baseline gap-2.5 text-[16px] font-semibold text-ink">
          Needs attention
          {items.length > 0 && <span className="text-[22px] font-semibold leading-none tabular-nums text-signal">{items.length}</span>}
        </h2>
        {items.length > 0 && <Link to="/followups"><Button>Open queue <ArrowRight className="h-4 w-4" aria-hidden /></Button></Link>}
      </header>
      {items.length === 0 ? (
        <p className="flex items-center gap-2.5 px-5 py-5 text-[13.5px] text-ink-2">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-good" aria-hidden />Nothing needs a person right now.
        </p>
      ) : (
        <>
          <ul className="divide-y divide-line-soft">
            {top.map((i) => (
              <li key={i.followup_id} className="px-5 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[14px] font-semibold text-ink">{i.participant_name}</span>
                  <Badge tone={i.priority === 1 ? "bad" : i.priority === 2 ? "warn" : "info"}>P{i.priority}</Badge>
                </div>
                <p className="mt-0.5 text-[13px] leading-relaxed text-ink-2">{i.recommended_action}</p>
              </li>
            ))}
          </ul>
          {more > 0 && <div className="border-t border-line-soft px-5 py-2.5 text-xs text-muted">+{more} more in the <Link className="font-medium text-ink underline decoration-ink/30 hover:decoration-ink" to="/followups">follow-up queue</Link></div>}
        </>
      )}
    </section>
  );
}
