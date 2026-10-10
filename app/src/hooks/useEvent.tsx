import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../services/api";
import type { EventInfo } from "../types";

interface Ctx { events: EventInfo[]; selected: EventInfo | null; loading: boolean; error: Error | null; select: (id: number) => void; reload: () => Promise<void> }
const EventCtx = createContext<Ctx | null>(null);

export function EventProvider({ children }: { children: ReactNode }) {
  const [events, setEvents] = useState<EventInfo[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const reload = useCallback(async () => {
    setLoading(true);
    try { setEvents(await api.events()); setError(null); } catch (e) { setError(e as Error); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  const selected = events.find((e) => e.id === selectedId) ?? events[0] ?? null;
  return <EventCtx.Provider value={{ events, selected, loading, error, select: setSelectedId, reload }}>{children}</EventCtx.Provider>;
}

export function useEvent(): Ctx {
  const c = useContext(EventCtx);
  if (!c) throw new Error("useEvent must be used inside EventProvider");
  return c;
}
