import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, BarChart3, CalendarDays, ChevronDown, Gauge, ListChecks, Megaphone, Search, Settings, Users, type LucideIcon } from "lucide-react";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { Badge, Loading } from "../components/ui";
import { ConfirmDialog, NotificationBell, ToastViewport } from "../components/Notifications";
import { useQueueWatcher } from "../hooks/useQueueWatcher";

interface NavItem { to: string; label: string; icon?: LucideIcon; end?: boolean; children?: { to: string; label: string; end?: boolean }[] }

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: Gauge, end: true },
  { to: "/campaigns", label: "Campaigns", icon: Megaphone },
  { to: "/followups", label: "Follow-up queue", icon: ListChecks },
  { to: "/leads", label: "People", icon: Users, children: [{ to: "/leads", label: "Leads" }, { to: "/participants", label: "Participants" }] },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/events", label: "Events", icon: CalendarDays },
];
const FOOT: NavItem[] = [{ to: "/settings", label: "Settings", icon: Settings }];

/** Every page (and a few actions) reachable from the command box. */
const COMMANDS: { label: string; to: string; hint: string }[] = [
  { label: "Dashboard", to: "/", hint: "Overview" }, { label: "Campaigns", to: "/campaigns", hint: "Run" }, { label: "New campaign", to: "/campaigns/new", hint: "Action" },
  { label: "Follow-up queue", to: "/followups", hint: "Run" }, { label: "Leads", to: "/leads", hint: "People" }, { label: "Participants", to: "/participants", hint: "People" },
  { label: "Analytics", to: "/analytics", hint: "Insight" }, { label: "Events", to: "/events", hint: "Setup" },
  { label: "Settings", to: "/settings", hint: "Setup" },
];

/** Three rings, a rhythm: the brand mark. */
function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
      <circle cx="16" cy="16" r="13" fill="none" stroke="#111113" strokeWidth="3.2" strokeDasharray="62 20" strokeLinecap="round" transform="rotate(-70 16 16)" />
      <circle cx="16" cy="16" r="7.6" fill="none" stroke="#e03a6b" strokeWidth="3.2" strokeDasharray="34 14" strokeLinecap="round" transform="rotate(20 16 16)" />
      <circle cx="16" cy="16" r="2.6" fill="#ffe53b" stroke="#111113" strokeWidth="1" />
    </svg>
  );
}

function CommandSearch() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [i, setI] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const hits = useMemo(() => COMMANDS.filter((c) => c.label.toLowerCase().includes(q.trim().toLowerCase())), [q]);
  useEffect(() => {
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);
  const go = (to: string) => { nav(to); setQ(""); setOpen(false); };
  return (
    <div ref={box} className="relative min-w-0 flex-1 basis-56 md:max-w-md">
      <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
      <input role="combobox" aria-expanded={open} aria-controls="cmd-list" aria-label="Search or type a command" value={q} placeholder="Search or type a command"
        onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true); setI(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setI((n) => Math.min(n + 1, hits.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setI((n) => Math.max(n - 1, 0)); }
          else if (e.key === "Enter" && hits[i]) go(hits[i].to);
          else if (e.key === "Escape") setOpen(false);
        }}
        className="w-full rounded-md border border-transparent bg-line-soft/70 py-2 pl-9 pr-3 text-[13px] text-ink placeholder:text-muted hover:bg-line-soft focus:border-ink focus:bg-surface focus:outline-none" />
      {open && (
        <ul id="cmd-list" role="listbox" className="panel-in absolute left-0 right-0 top-full z-30 mt-1.5 overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-[0_12px_32px_-12px_rgba(17,17,19,.25)]">
          {hits.length === 0 && <li className="px-3 py-2 text-[13px] text-muted">No match</li>}
          {hits.map((c, n) => (
            <li key={c.to + c.label} role="option" aria-selected={n === i}>
              <button type="button" onMouseEnter={() => setI(n)} onClick={() => go(c.to)}
                className={`flex w-full items-center justify-between px-3 py-2 text-left text-[13px] ${n === i ? "bg-canvas" : ""}`}>
                <span className="font-medium text-ink">{c.label}</span><span className="text-xs text-muted">{c.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NavGroup({ item, count }: { item: NavItem; count?: number }) {
  const { pathname } = useLocation();
  const within = !!item.children?.some((c) => (c.end ? pathname === c.to : pathname.startsWith(c.to)));
  const [open, setOpen] = useState(within);
  useEffect(() => { if (within) setOpen(true); }, [within]);
  const Icon = item.icon;
  const base = "group flex items-center gap-2.5 whitespace-nowrap rounded-md px-3 py-2 text-[13.5px] transition-colors duration-150";
  if (!item.children) {
    return (
      <NavLink to={item.to} end={item.end} className={({ isActive }) => `${base} ${isActive ? "bg-canvas font-semibold text-ink" : "text-ink-2 hover:bg-canvas hover:text-ink"}`}>
        {Icon && <Icon className="h-4 w-4" aria-hidden />}<span className="flex-1">{item.label}</span>
        {!!count && <span className="rounded-[5px] bg-marigold px-1.5 text-[11px] font-semibold leading-5 text-ink">{count}</span>}
      </NavLink>
    );
  }
  return (
    <div>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
        className={`${base} w-full ${within ? "bg-canvas font-semibold text-ink" : "text-ink-2 hover:bg-canvas hover:text-ink"}`}>
        {Icon && <Icon className="h-4 w-4" aria-hidden />}<span className="flex-1 text-left">{item.label}</span>
        <ChevronDown aria-hidden className={`h-4 w-4 text-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="expand-in ml-[22px] mt-0.5 space-y-0.5 border-l border-line pl-2">
          {item.children.map((c) => (
            <NavLink key={c.to} to={c.to} end={c.end} className={({ isActive }) => `block rounded-md px-3 py-1.5 text-[13px] ${isActive ? "bg-canvas font-semibold text-ink" : "text-muted hover:text-ink"}`}>{c.label}</NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AppLayout() {
  const { data } = useAsync(() => api.settings(), []);
  const { events, selected, select } = useEvent();
  const { pathname } = useLocation();
  const queue = useAsync(() => (selected ? api.followupQueue({ eventId: selected.id }) : Promise.resolve([])), [selected?.id, pathname]);
  useQueueWatcher(selected?.id);
  const simulated = data?.provider === "demo";
  const crumb = [...NAV.flatMap((n) => [n, ...(n.children ?? []).map((c) => ({ ...c, parent: n.label }))]), ...FOOT]
    .filter((n) => (n.to === "/" ? pathname === "/" : pathname.startsWith(n.to))).sort((a, b) => b.to.length - a.to.length)[0] as ({ label: string; parent?: string } | undefined);
  return (
    <div className="min-h-screen md:grid md:grid-cols-[15.5rem_minmax(0,1fr)]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-white focus:p-2">Skip to content</a>
      <aside className="border-b border-line bg-sidebar md:sticky md:top-0 md:flex md:h-screen md:flex-col md:border-b-0 md:border-r">
        <div className="flex items-center gap-2.5 px-5 pb-3 pt-5 md:pb-6">
          <Mark />
          <div className="text-[19px] font-bold leading-none tracking-[-0.03em] text-ink">Cadence</div>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:overflow-y-auto md:overflow-x-visible md:pb-4">
          {NAV.map((n) => <NavGroup key={n.label} item={n} count={n.to === "/followups" ? queue.data?.length : undefined} />)}
        </nav>
        <div className="hidden border-t border-line px-3 py-3 md:block">
          {FOOT.map((n) => <NavGroup key={n.label} item={n} />)}
          {data && (
            <div className="mt-2 flex items-center gap-2 px-3 py-2 text-xs text-muted">
              <i aria-hidden className={`h-2 w-2 rounded-full ${simulated ? "bg-marigold ring-1 ring-ink/30" : "bg-good"}`} />
              {simulated ? "Demo — calls simulated" : `Calling via ${data.provider}`}
            </div>
          )}
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-surface/90 px-4 py-2.5 backdrop-blur md:px-8">
          <CommandSearch />
          <div className="ml-auto flex items-center gap-3">
            <label htmlFor="event-select" className="sr-only">Event</label>
            <select id="event-select" value={selected?.id ?? ""} onChange={(e) => select(Number(e.target.value))} disabled={events.length === 0}
              className="max-w-[16rem] truncate rounded-md border border-line bg-surface px-3 py-1.5 text-[13px] font-medium text-ink transition-colors hover:border-ink/40 focus:border-ink focus:outline-none">
              {events.length === 0 && <option value="">No events yet</option>}
              {events.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
            <NotificationBell />
          </div>
        </header>
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line bg-surface px-4 py-2.5 text-[13px] md:px-8">
          <div className="flex items-center gap-2 text-muted">
            <Link to="/" aria-label="Back to dashboard" className="grid h-6 w-6 place-items-center rounded-md text-ink hover:bg-canvas"><ArrowLeft className="h-4 w-4" aria-hidden /></Link>
            {crumb?.parent && <><span>{crumb.parent}</span><span aria-hidden>›</span></>}
            <span className="font-medium text-ink">{crumb?.label ?? "Cadence"}</span>
            {selected && <><span aria-hidden>›</span><span className="max-w-[22rem] truncate">{selected.name}</span></>}
          </div>
          {selected?.is_demo && <Badge tone="warn">Sample event: fictional participants, simulated calls</Badge>}
        </div>
        <main id="main" className="px-4 py-7 md:px-8">
          <div key={pathname} className="page-in mx-auto max-w-6xl"><Suspense fallback={<Loading />}><Outlet /></Suspense></div>
        </main>
        <ToastViewport />
        <ConfirmDialog />
      </div>
    </div>
  );
}
