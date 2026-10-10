import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../services/api";
import type { EventInfo } from "../types";

interface Ctx {
  events: EventInfo[]; selected: EventInfo | null; loading: boolean; error: Error | null;
  select: (id: number) => void; reload: () => Promise<EventInfo[]>;
}
const EventCtx = createContext<Ctx | null>(null);
const KEY = "cadence.selectedEvent";

function readStored(): number | null {
  try { const v = localStorage.getItem(KEY); return v ? Number(v) : null; } catch { return null; }
}

export function EventProvider({ children }: { children: ReactNode }) {
  const [events, setEvents] = useState<EventInfo[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(readStored);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try { const e = await api.events(); setEvents(e); setError(null); return e; }
    catch (err) { setError(err as Error); return []; }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);

  const select = (id: number) => {
    setSelectedId(id);
    try { localStorage.setItem(KEY, String(id)); } catch { /* storage unavailable */ }
  };
  const selected = events.find((e) => e.id === selectedId) ?? events[0] ?? null;
  return <EventCtx.Provider value={{ events, selected, loading, error, select, reload }}>{children}</EventCtx.Provider>;
}

export function useEvent(): Ctx {
  const c = useContext(EventCtx);
  if (!c) throw new Error("useEvent must be used inside EventProvider");
  return c;
}
