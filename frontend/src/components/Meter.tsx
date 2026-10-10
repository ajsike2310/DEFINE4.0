import { useMounted } from "../hooks/useCountUp";
import { pct } from "../services/labels";

/** One labelled horizontal bar. `value` is 0..1 or null (undefined: no data, shown as a dash, never a fake 0). */
export function Meter({ label, value, hint, tone = "brand" }: { label: string; value: number | null; hint?: string; tone?: "brand" | "bad" | "signal" }) {
  const mounted = useMounted();
  const fill = { brand: "bg-brand", bad: "bg-bad/70", signal: "bg-signal" }[tone];
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-[13px]">
        <span className="text-ink-2">{label}</span>
        <span className="font-medium tabular-nums text-ink">{pct(value)}</span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-[2px] bg-line-soft" role="img" aria-label={`${label}: ${pct(value)}`}>
        <div className={`h-full ${fill} transition-[width] duration-[900ms] ease-[var(--ease-out-soft)]`}
          style={{ width: mounted && value != null ? `${Math.min(value, 1) * 100}%` : "0%" }} />
      </div>
      {hint && <div className="mt-1 text-[11.5px] leading-snug text-muted">{hint}</div>}
    </div>
  );
}

/** Count bars for a {label: count} distribution. */
export function Distribution({ rows, total }: { rows: { label: string; count: number }[]; total: number }) {
  const mounted = useMounted();
  if (total === 0) return <p className="text-[13px] text-muted">Nothing recorded yet.</p>;
  return (
    <ul className="space-y-2">
      {rows.filter((r) => r.count > 0).map((r) => (
        <li key={r.label} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-[13px]">
          <span className="truncate text-ink-2">{r.label}</span>
          <span className="h-2 overflow-hidden rounded-[2px] bg-line-soft">
            <span className="block h-full bg-brand/80 transition-[width] duration-[900ms] ease-[var(--ease-out-soft)]"
              style={{ width: mounted ? `${(r.count / total) * 100}%` : "0%" }} />
          </span>
          <span className="w-10 text-right tabular-nums text-ink">{r.count}</span>
        </li>
      ))}
    </ul>
  );
}
