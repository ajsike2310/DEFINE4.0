import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, AlertTriangle, Bell, CheckCircle2, Info, X } from "lucide-react";
import { useNotify, type HistoryItem, type NotifyAction, type NotifyTone, type Toast } from "../hooks/useNotify";

const TONE: Record<NotifyTone, { icon: typeof Info; text: string; rail: string; bar: string }> = {
  success: { icon: CheckCircle2, text: "text-good", rail: "bg-good", bar: "bg-good/40" },
  error: { icon: AlertCircle, text: "text-bad", rail: "bg-bad", bar: "bg-bad/40" },
  info: { icon: Info, text: "text-info", rail: "bg-info", bar: "bg-info/40" },
  warn: { icon: AlertTriangle, text: "text-warn", rail: "bg-warn", bar: "bg-warn/40" },
};

export function relativeTime(at: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - at) / 1000));
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(at).toLocaleDateString();
}

function useRunAction() {
  const nav = useNavigate();
  return (a?: NotifyAction) => { if (!a) return; if (a.to) nav(a.to); a.onClick?.(); };
}

function ToastItem({ t }: { t: Toast }) {
  const { dismiss } = useNotify();
  const run = useRunAction();
  const [paused, setPaused] = useState(false);
  const remaining = useRef(t.duration);
  const started = useRef(0);
  const { icon: Icon, text, rail, bar } = TONE[t.tone];

  // auto-dismiss; hovering or focusing the toast pauses the countdown
  useEffect(() => {
    if (!t.duration || paused || t.leaving) return;
    started.current = Date.now();
    const h = setTimeout(() => dismiss(t.id), remaining.current);
    return () => { clearTimeout(h); remaining.current = Math.max(0, remaining.current - (Date.now() - started.current)); };
  }, [paused, t.duration, t.leaving, t.id, dismiss]);

  return (
    <div role={t.tone === "error" ? "alert" : "status"}
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)} onBlur={() => setPaused(false)}
      className={`${t.leaving ? "toast-out" : "toast-in"} pointer-events-auto relative overflow-hidden rounded-lg border border-line bg-surface shadow-[0_8px_28px_rgba(15,35,32,.16)]`}>
      <span aria-hidden className={`absolute inset-y-0 left-0 w-1 ${rail}`} />
      <div className="flex items-start gap-3 py-3 pl-5 pr-3">
        <Icon aria-hidden className={`mt-0.5 h-[18px] w-[18px] shrink-0 ${text}`} />
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-semibold leading-snug text-ink">{t.title}</p>
          {t.message && <p className="mt-0.5 break-words text-[13px] leading-snug text-ink-2">{t.message}</p>}
          {t.action && (
            <button type="button" onClick={() => { run(t.action); dismiss(t.id); }}
              className="press mt-2 rounded px-0.5 text-[13px] font-medium text-ink underline decoration-ink/30 hover:decoration-ink-offset-2 hover:underline">{t.action.label}</button>
          )}
        </div>
        <button type="button" onClick={() => dismiss(t.id)} aria-label="Dismiss notification"
          className="press -mr-1 rounded p-1 text-muted hover:bg-line-soft hover:text-ink"><X className="h-4 w-4" /></button>
      </div>
      {t.duration > 0 && (
        <span aria-hidden className={`toast-progress absolute bottom-0 left-0 h-[2px] w-full origin-left ${bar}`}
          style={{ animationDuration: `${t.duration}ms`, animationPlayState: paused ? "paused" : "running" }} />
      )}
    </div>
  );
}

export function ToastViewport() {
  const { toasts } = useNotify();
  return (
    <section aria-label="Notifications" className="pointer-events-none fixed inset-x-3 bottom-3 z-50 flex flex-col gap-2 sm:inset-x-auto sm:right-5 sm:bottom-5 sm:w-[390px]">
      {toasts.map((t) => <ToastItem key={t.id} t={t} />)}
    </section>
  );
}

function CenterItem({ n, onGo }: { n: HistoryItem; onGo: () => void }) {
  const { icon: Icon, text } = TONE[n.tone];
  const run = useRunAction();
  return (
    <li className={`flex gap-3 px-4 py-3 transition-colors ${n.read ? "" : "bg-brand-soft/50"}`}>
      <Icon aria-hidden className={`mt-0.5 h-4 w-4 shrink-0 ${text}`} />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium leading-snug text-ink">{n.title}</p>
        {n.message && <p className="mt-0.5 break-words text-xs leading-snug text-ink-2">{n.message}</p>}
        <div className="mt-1 flex items-center gap-3 text-xs text-muted">
          <time dateTime={new Date(n.at).toISOString()}>{relativeTime(n.at)}</time>
          {n.action && <button type="button" className="font-medium text-ink underline decoration-ink/30 hover:decoration-ink" onClick={() => { run(n.action); onGo(); }}>{n.action.label}</button>}
        </div>
      </div>
      {!n.read && <i aria-label="Unread" className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-signal" />}
    </li>
  );
}

/** Bell with an unread count and a history panel (notification centre). */
export function NotificationBell() {
  const { history, unread, markAllRead, clearHistory } = useNotify();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  const close = () => { setOpen(false); markAllRead(); };
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) close(); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("mousedown", onDown); document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <div ref={box} className="relative ml-auto">
      <button type="button" aria-haspopup="dialog" aria-expanded={open}
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        onClick={() => (open ? close() : setOpen(true))}
        className="press relative grid h-9 w-9 place-items-center rounded-lg border border-line bg-surface text-ink-2 hover:border-ink-2/40 hover:text-ink">
        <Bell className="h-[17px] w-[17px]" />
        {unread > 0 && (
          <span key={unread} className="badge-pop absolute -right-1.5 -top-1.5 grid min-w-[18px] place-items-center rounded-full bg-signal px-1 text-[11px] font-semibold leading-[18px] text-white">{unread > 9 ? "9+" : unread}</span>
        )}
      </button>
      {open && (
        <div role="dialog" aria-label="Notification centre" className="panel-in absolute right-0 top-full z-40 mt-2 w-[min(92vw,25rem)] overflow-hidden rounded-lg border border-line bg-surface shadow-[0_12px_36px_rgba(15,35,32,.18)]">
          <header className="flex items-center justify-between border-b border-line-soft px-4 py-2.5">
            <h2 className="text-[13px] font-semibold text-ink">Notifications</h2>
            <div className="flex gap-3 text-xs">
              <button type="button" disabled={unread === 0} onClick={markAllRead} className="font-medium text-ink underline decoration-ink/30 hover:decoration-ink disabled:text-muted disabled:no-underline">Mark all read</button>
              <button type="button" disabled={history.length === 0} onClick={clearHistory} className="font-medium text-ink-2 hover:underline disabled:text-muted disabled:no-underline">Clear</button>
            </div>
          </header>
          {history.length === 0 ? (
            <p className="px-4 py-10 text-center text-[13px] text-muted">Nothing yet. Results of your actions and new follow-ups appear here.</p>
          ) : (
            <ul className="max-h-[min(60vh,28rem)] divide-y divide-line-soft overflow-y-auto">
              {history.map((n) => <CenterItem key={n.id} n={n} onGo={() => setOpen(false)} />)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** Replaces window.confirm(): modal dialog, Esc / backdrop / Cancel = no. Danger confirmations focus Cancel first. */
export function ConfirmDialog() {
  const { pendingConfirm: p, resolveConfirm } = useNotify();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const okRef = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!p) return;
    opener.current = document.activeElement as HTMLElement | null;
    (p.danger ? cancelRef : okRef).current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); resolveConfirm(false); }
      if (e.key === "Tab") {                         // keep focus inside the two buttons
        const order = [cancelRef.current, okRef.current].filter(Boolean) as HTMLElement[];
        const i = order.indexOf(document.activeElement as HTMLElement);
        e.preventDefault();
        order[(i + (e.shiftKey ? -1 : 1) + order.length) % order.length].focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); opener.current?.focus?.(); };
  }, [p, resolveConfirm]);

  if (!p) return null;
  return (
    <div className="fade-in fixed inset-0 z-[60] grid place-items-center bg-ink/45 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) resolveConfirm(false); }}>
      <div role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby={p.message ? "confirm-desc" : undefined}
        className="dialog-in w-full max-w-md rounded-lg border border-line bg-surface p-6 shadow-[0_20px_60px_rgba(15,35,32,.28)]">
        <h2 id="confirm-title" className="text-base font-semibold text-ink">{p.title}</h2>
        {p.message && <p id="confirm-desc" className="mt-2 text-[13.5px] leading-relaxed text-ink-2">{p.message}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <button ref={cancelRef} type="button" onClick={() => resolveConfirm(false)}
            className="press rounded-lg border border-line bg-surface px-3.5 py-2 text-[13px] font-medium text-ink hover:border-ink-2/40">{p.cancelLabel ?? "Cancel"}</button>
          <button ref={okRef} type="button" onClick={() => resolveConfirm(true)}
            className={`press rounded-lg px-3.5 py-2 text-[13px] font-medium text-white ${p.danger ? "bg-bad hover:bg-[#8c3426]" : "bg-brand hover:bg-brand-ink"}`}>{p.confirmLabel ?? "Confirm"}</button>
        </div>
      </div>
    </div>
  );
}
