import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api";
import { useEvent } from "../hooks/useEvent";
import { useNotify } from "../hooks/useNotify";
import { Button, Card, Empty, ErrorState, Loading } from "./ui";

/** Sample-data actions shared by the empty state and Settings. */
export function SampleButtons() {
  const { reload, select } = useEvent();
  const { success, error } = useNotify();
  const [busy, setBusy] = useState(false);
  async function load(run: boolean) {
    setBusy(true);
    try {
      const r = await api.seedAll(run);
      await reload();
      if (r.events[0]) select(r.events[0].id);
      if (run) success("Sample events loaded and simulated", "Three sample events with finished simulated calls. Every call is labelled Simulated.", { action: { label: "Open dashboard", to: "/" } });
      else success("Sample events loaded", "Open a campaign and press Start to watch the simulation.", { action: { label: "View campaigns", to: "/campaigns" } });
    } catch (e) { error("Could not load the sample events", (e as Error).message); } finally { setBusy(false); }
  }
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="flex flex-wrap justify-center gap-2">
        <Button disabled={busy} onClick={() => load(true)}>{busy ? "Working…" : "Load sample events and run simulation"}</Button>
        <Button variant="secondary" disabled={busy} onClick={() => load(false)}>Load sample events (not started)</Button>
      </div>
    </div>
  );
}

/** Shown by event-scoped pages until an event exists. Returns null when an event is selected. */
export function NoEvent() {
  const { selected, loading, error, reload } = useEvent();
  if (loading && !selected) return <Loading />;
  if (error) return <ErrorState error={error} retry={() => void reload()} />;
  if (selected) return null;
  return (
    <Card>
      <Empty title="No event yet" body="Cadence works per event. Load three clearly labelled sample events (fictional participants, simulated calls) or create your own."
        action={<div className="flex flex-col items-center gap-3"><SampleButtons /><Link to="/events"><Button variant="secondary">Create my own event</Button></Link></div>} />
    </Card>
  );
}
