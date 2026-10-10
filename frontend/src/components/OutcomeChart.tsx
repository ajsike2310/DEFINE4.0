import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Analytics } from "../types";
import { LANG_LABEL } from "../services/labels";
import { Table } from "./ui";

/** Outcomes grouped by meaning: green = attending, marigold = acknowledged, indigo = open request,
 *  hibiscus = needs a person, rust = declined, sage = not reached. Shared by the carpet and the bars. */
export const GROUPS: { key: string; label: string; members: string[]; color: string }[] = [
  { key: "attending", label: "Attending", members: ["confirmed"], color: "var(--color-good)" },
  { key: "acknowledged", label: "Acknowledged", members: ["acknowledged"], color: "var(--color-marigold)" },
  { key: "open", label: "Callback or info requested", members: ["callback_requested", "information_requested"], color: "var(--color-thumbi)" },
  { key: "human", label: "Needs human", members: ["unclear", "human_required"], color: "var(--color-signal)" },
  { key: "declined", label: "Declined or opted out", members: ["declined", "opted_out"], color: "var(--color-bad)" },
  { key: "none", label: "Not reached", members: ["no_response"], color: "#b9b9c0" },
];

const reduced = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function OutcomeByLanguage({ rows }: { rows: Analytics["by_language"] }) {
  const data = rows.map((r) => {
    const row: Record<string, number | string> = { name: LANG_LABEL[r.language] ?? r.language };
    for (const g of GROUPS) row[g.key] = g.members.reduce((n, m) => n + (Number(r[m]) || 0), 0);
    return row;
  });
  return (
    <div>
      <div aria-hidden style={{ height: 56 + data.length * 46 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" stackOffset="expand" margin={{ left: 4, right: 8, top: 0, bottom: 0 }} barCategoryGap="28%">
            <CartesianGrid horizontal={false} stroke="var(--color-line-soft)" />
            <XAxis type="number" tickFormatter={(v: number) => `${Math.round(v * 100)}%`} tickLine={false} axisLine={false} fontSize={12} stroke="var(--color-muted)" />
            <YAxis type="category" dataKey="name" width={92} tickLine={false} axisLine={false} fontSize={12.5} stroke="var(--color-ink-2)" />
            <Tooltip cursor={{ fill: "rgba(17,17,19,0.05)" }} contentStyle={{ border: "1px solid var(--color-line)", borderRadius: 10, fontSize: 12, boxShadow: "none" }} />
            {GROUPS.map((g) => <Bar key={g.key} dataKey={g.key} name={g.label} stackId="a" fill={g.color}
              isAnimationActive={!reduced()} animationDuration={800} animationEasing="ease-out" />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        {GROUPS.map((g) => <li key={g.key} className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-[2px]" style={{ background: g.color }} />{g.label}</li>)}
      </ul>
      <details className="mt-4 text-[13px]">
        <summary className="cursor-pointer text-xs font-medium text-ink underline decoration-ink/30 hover:decoration-ink">View as table</summary>
        <div className="mt-2 rounded-lg border border-line">
          <Table head={["Language", ...GROUPS.map((g) => g.label)]}>
            {data.map((r) => (
              <tr key={String(r.name)}><td className="font-medium">{r.name}</td>{GROUPS.map((g) => <td key={g.key} className="tabular-nums">{r[g.key]}</td>)}</tr>
            ))}
          </Table>
        </div>
      </details>
    </div>
  );
}
