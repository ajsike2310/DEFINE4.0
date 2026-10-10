import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

export type NotifyTone = "success" | "error" | "info" | "warn";
export interface NotifyAction { label: string; to?: string; onClick?: () => void }
export interface NotifyInput {
  tone?: NotifyTone; title: string; message?: string; action?: NotifyAction;
  /** ms before auto-dismiss; 0 = stays until dismissed. Defaults: 5s, errors 9s. */
  duration?: number;
  /** false = show the toast only (not kept in the notification centre) */
  keep?: boolean;
}
export interface Toast { id: number; tone: NotifyTone; title: string; message?: string; action?: NotifyAction; duration: number; leaving?: boolean }
export interface HistoryItem { id: number; tone: NotifyTone; title: string; message?: string; at: number; read: boolean; action?: NotifyAction }
export interface ConfirmOptions { title: string; message?: string; confirmLabel?: string; cancelLabel?: string; danger?: boolean }
interface PendingConfirm extends ConfirmOptions { resolve: (ok: boolean) => void }

interface Ctx {
  toasts: Toast[]; history: HistoryItem[]; unread: number; pendingConfirm: PendingConfirm | null;
  notify: (n: NotifyInput) => number;
  success: (title: string, message?: string, extra?: Partial<NotifyInput>) => number;
  error: (title: string, message?: string, extra?: Partial<NotifyInput>) => number;
  info: (title: string, message?: string, extra?: Partial<NotifyInput>) => number;
  warn: (title: string, message?: string, extra?: Partial<NotifyInput>) => number;
  dismiss: (id: number) => void;
  markAllRead: () => void; clearHistory: () => void;
  confirm: (o: ConfirmOptions) => Promise<boolean>;
  resolveConfirm: (ok: boolean) => void;
}
const NotifyCtx = createContext<Ctx | null>(null);

const MAX_TOASTS = 4, MAX_HISTORY = 50, EXIT_MS = 220, KEY = "cadence.notifications";

function load(): HistoryItem[] {
  try { const raw = localStorage.getItem(KEY); return raw ? (JSON.parse(raw) as HistoryItem[]).slice(0, MAX_HISTORY) : []; } catch { return []; }
}
function save(h: HistoryItem[]) {
  try { localStorage.setItem(KEY, JSON.stringify(h.map(({ action, ...rest }) => ({ ...rest, action: action?.to ? { label: action.label, to: action.to } : undefined })))); } catch { /* storage unavailable */ }
}

export function NotifyProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>(load);
  const [pendingConfirm, setPending] = useState<PendingConfirm | null>(null);
  const nextId = useRef(1);
  const recent = useRef(new Map<string, number>());

  const dismiss = useCallback((id: number) => {
    setToasts((ts) => ts.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    setTimeout(() => setToasts((ts) => ts.filter((t) => t.id !== id)), EXIT_MS);
  }, []);

  const notify = useCallback((n: NotifyInput) => {
    const tone = n.tone ?? "info";
    const sig = `${tone}|${n.title}|${n.message ?? ""}`;
    const now = Date.now();
    const last = recent.current.get(sig);
    if (last && now - last < 1500) return -1;                 // identical toast a moment ago (double fire): ignore
    recent.current.set(sig, now);
    const id = nextId.current++;
    const duration = n.duration ?? (tone === "error" ? 9000 : 5000);
    setToasts((ts) => [...ts, { id, tone, title: n.title, message: n.message, action: n.action, duration }].slice(-MAX_TOASTS));
    if (n.keep !== false) {
      setHistory((h) => { const next = [{ id: now + id, tone, title: n.title, message: n.message, at: now, read: false, action: n.action }, ...h].slice(0, MAX_HISTORY); save(next); return next; });
    }
    return id;
  }, []);

  const make = (tone: NotifyTone) => (title: string, message?: string, extra?: Partial<NotifyInput>) => notify({ ...extra, tone, title, message });
  const markAllRead = useCallback(() => setHistory((h) => { const next = h.map((i) => ({ ...i, read: true })); save(next); return next; }), []);
  const clearHistory = useCallback(() => { setHistory([]); save([]); }, []);

  const confirm = useCallback((o: ConfirmOptions) => new Promise<boolean>((resolve) => setPending({ ...o, resolve })), []);
  const resolveConfirm = useCallback((ok: boolean) => setPending((p) => { p?.resolve(ok); return null; }), []);

  const value = useMemo<Ctx>(() => ({
    toasts, history, unread: history.filter((h) => !h.read).length, pendingConfirm, notify,
    success: make("success"), error: make("error"), info: make("info"), warn: make("warn"),
    dismiss, markAllRead, clearHistory, confirm, resolveConfirm,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [toasts, history, pendingConfirm, notify, dismiss, markAllRead, clearHistory, confirm, resolveConfirm]);

  return <NotifyCtx.Provider value={value}>{children}</NotifyCtx.Provider>;
}

export function useNotify(): Ctx {
  const c = useContext(NotifyCtx);
  if (!c) throw new Error("useNotify must be used inside NotifyProvider");
  return c;
}
