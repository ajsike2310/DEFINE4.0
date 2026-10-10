import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Inbox } from "lucide-react";
import type { Tone } from "../services/labels";
import { useCountUp } from "../hooks/useCountUp";

const TONES: Record<Tone, string> = {
  good: "text-good bg-good/10",
  bad: "text-bad bg-bad/10",
  warn: "text-warn bg-marigold/45",
  info: "text-info bg-info/10",
  neutral: "text-ink-2 bg-line-soft",
};

/** Status marker: a small tinted chip with a dot. Colour is the tone, the label is the meaning. */
export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-[5px] px-1.5 py-0.5 text-[11.5px] font-medium leading-4 ${TONES[tone]}`}>
      <i aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />{children}
    </span>
  );
}

export function SimBadge({ simulated }: { simulated: boolean }) {
  return simulated ? <Badge tone="warn">Simulated</Badge> : <Badge tone="good">Real</Badge>;
}

/** Entrance animation with optional stagger index. */
export function Reveal({ i = 0, className = "", children }: { i?: number; className?: string; children: ReactNode }) {
  return <div className={`reveal ${className}`} style={{ "--i": i } as CSSProperties}>{children}</div>;
}

export function Card({ title, action, children, flush }: { title?: string; action?: ReactNode; children: ReactNode; flush?: boolean }) {
  return (
    <section className="min-w-0 rounded-lg border border-line bg-surface">
      {title && (
        <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line-soft px-5 py-3">
          <h2 className="text-[14px] font-semibold text-ink">{title}</h2>{action}
        </header>
      )}
      <div className={flush ? "" : "p-5"}>{children}</div>
    </section>
  );
}

/** Hairline-divided metric strip: one bordered frame, cells split by 1px rules. */
export function StatGrid({ label, cols = 4, children }: { label?: string; cols?: 2 | 3 | 4 | 5; children: ReactNode }) {
  const grid = { 2: "grid-cols-2", 3: "grid-cols-2 md:grid-cols-3", 4: "grid-cols-2 md:grid-cols-4", 5: "grid-cols-2 md:grid-cols-5" }[cols];
  return (
    <div>
      {label && <h2 className="mb-2.5 text-[14px] font-semibold text-ink">{label}</h2>}
      <div className={`grid ${grid} gap-px overflow-hidden rounded-lg border border-line bg-line`}>{children}</div>
    </div>
  );
}

export function Stat({ label, value, hint, accent, to }: { label: string; value: ReactNode; hint?: string; accent?: boolean; to?: string }) {
  const n = typeof value === "number" ? value : null;
  const shown = useCountUp(n ?? 0);
  const body = (<>
    <div className="text-xs text-muted">{label}</div>
    <div className={`mt-1.5 flex items-center gap-2 text-[28px] font-semibold leading-none tracking-tight tabular-nums ${accent ? "text-signal" : "text-ink"}`}>
      {n === null ? value : shown}{accent && <i aria-hidden className="h-2 w-2 rounded-full bg-signal" />}
    </div>
    {hint && <div className="mt-2 text-[11.5px] leading-snug text-muted">{hint}</div>}
  </>);
  const cls = "block bg-surface px-4 py-4";
  return to
    ? <Link to={to} className={`${cls} press transition-colors hover:bg-canvas focus-visible:relative focus-visible:z-10`}>{body}</Link>
    : <div className={cls}>{body}</div>;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
      <div className="min-w-0">
        <h1 className="text-[24px] font-semibold leading-tight tracking-[-0.02em] text-ink text-balance">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-[13.5px] leading-relaxed text-muted">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  );
}

export function Button({ variant = "primary", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  const v = {
    primary: "bg-ink text-white hover:bg-ink-2",
    secondary: "border border-ink/80 bg-surface text-ink hover:bg-canvas",
    danger: "border border-bad/50 bg-surface text-bad hover:bg-bad/8",
    ghost: "text-ink-2 hover:bg-line-soft",
  }[variant];
  return <button {...p} className={`press inline-flex items-center gap-2 rounded-md px-3.5 py-2 text-[13px] font-medium disabled:cursor-not-allowed disabled:opacity-45 ${v} ${p.className ?? ""}`} />;
}

export const inputCls = "w-full rounded-md border border-line bg-surface px-3 py-2 text-[13.5px] text-ink transition-[border-color,box-shadow] duration-150 placeholder:text-muted hover:border-ink/40 focus:border-ink focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-marigold)_55%,transparent)] focus:outline-none";

export function Field({ label, error, hint, children }: { label: string; error?: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 block text-[12.5px] font-medium text-ink-2">{label}</span>
      {children}
      {hint && !error && <span className="mt-1.5 block text-xs leading-snug text-muted">{hint}</span>}
      {error && <span role="alert" className="drop-in mt-1.5 block text-xs font-medium text-bad">{error}</span>}
    </label>
  );
}

/** Underline tabs: the selected one is black with a 2px rule. */
export function Segmented<T extends string>({ options, value, onChange, label }: { options: [T, string][]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex gap-5 border-b border-line">
      {options.map(([k, l]) => (
        <button key={k} type="button" aria-pressed={value === k} onClick={() => onChange(k)}
          className={`press -mb-px border-b-2 pb-2 pt-1 text-[13px] font-medium ${value === k ? "border-ink text-ink" : "border-transparent text-muted hover:text-ink"}`}>{l}</button>
      ))}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />;
}

export function Loading() {
  return (
    <div role="status" aria-label="Loading" className="space-y-7 py-2">
      <span className="sr-only">Loading…</span>
      <Skeleton className="h-36" />
      <Skeleton className="h-44" />
      <div className="grid grid-cols-2 gap-px md:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[92px]" />)}</div>
    </div>
  );
}

export function ErrorState({ error, retry, title = "Could not load this" }: { error: Error; retry?: () => void; title?: string }) {
  return (
    <div role="alert" className="drop-in flex items-start gap-3 rounded-lg border border-bad/30 bg-bad/6 p-4 text-sm text-bad">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1"><div className="font-medium">{title}</div><div className="text-ink-2">{error.message}</div><div className="mt-0.5 text-xs text-muted">Check that the Cadence backend is running, then retry.</div></div>
      {retry && <Button variant="secondary" onClick={retry}>Retry</Button>}
    </div>
  );
}

export function Empty({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-14 text-center">
      <span className="mb-1 grid h-10 w-10 place-items-center rounded-full bg-marigold text-ink"><Inbox className="h-[18px] w-[18px]" /></span>
      <div className="text-base font-semibold text-ink">{title}</div>
      <p className="max-w-sm text-[13px] leading-relaxed text-muted">{body}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Notice({ tone = "neutral", children }: { tone?: "good" | "bad" | "neutral"; children: ReactNode }) {
  const c = { good: "border-good/30 bg-good/8", bad: "border-bad/30 bg-bad/8", neutral: "border-line bg-surface" }[tone];
  return <div role="status" className={`drop-in mb-4 rounded-lg border px-4 py-2.5 text-[13px] text-ink-2 ${c}`}>{children}</div>;
}

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="tbl w-full text-left text-[13px]">
        <thead className="border-b border-line-soft">
          <tr>{head.map((h, i) => <th key={`${i}-${h}`} className="px-4 py-2.5 text-xs font-medium text-muted">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-line-soft [&_td]:px-4 [&_td]:py-3 [&_td]:align-middle">{children}</tbody>
      </table>
    </div>
  );
}
