import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useNavigate } from "react-router-dom";
import { GROUPS } from "./OutcomeChart";

/** Where a click on a bar leads, for the groups that have a matching participant filter. */
const DRILL: Record<string, string> = { human: "/participants?filter=attention", open: "/participants?filter=callback", declined: "/participants?filter=optout" };

const reduced = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** One horizontal bar per response group. Hover for the count and share; click a bar to open the matching people. */
export function ResponsesChart({ outcomes, total }: { outcomes: Record<string, number>; total: number }) {
  const nav = useNavigate();
  const data = GROUPS.map((g) => ({ key: g.key, name: g.label, color: g.color, value: g.members.reduce((n, m) => n + (outcomes[m] ?? 0), 0) }));
  return (
    <div>
      <div style={{ height: 40 + data.length * 38 }} aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 0, right: 28, top: 4, bottom: 4 }} barCategoryGap="26%">
            <XAxis type="number" hide domain={[0, "dataMax"]} />
            <YAxis type="category" dataKey="name" width={170} tickLine={false} axisLine={false} fontSize={12.5} stroke="var(--color-ink-2)" />
            <Tooltip cursor={{ fill: "rgba(17,17,19,0.05)" }} contentStyle={{ border: "1px solid var(--color-line)", borderRadius: 8, fontSize: 12, boxShadow: "none" }}
              formatter={(v: number) => [`${v} of ${total} (${total ? Math.round((v / total) * 100) : 0}%)`, "People"]} />
            <Bar dataKey="value" radius={[0, 5, 5, 0]} isAnimationActive={!reduced()} animationDuration={700} animationEasing="ease-out"
              onClick={(d: { key?: string }) => { const to = d.key ? DRILL[d.key] : undefined; if (to) nav(to); }}>
              {data.map((d) => <Cell key={d.key} fill={d.color} cursor={DRILL[d.key] ? "pointer" : "default"} />)}
              <LabelList dataKey="value" position="right" fontSize={12.5} fill="var(--color-ink)" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="sr-only">{data.map((d) => <li key={d.key}>{d.name}: {d.value}</li>)}</ul>
      <p className="mt-1 text-xs text-muted">Click “Needs human”, “Callback or info requested” or “Declined or opted out” to see those people.</p>
    </div>
  );
}
