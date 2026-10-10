import { Fragment, useState } from "react";
import { api } from "../services/api";
import { useEvent } from "../hooks/useEvent";
import { Badge, Button, Card, Field, PageHeader, inputCls } from "../components/ui";
import type { EventInfo } from "../types";

const INFO_FIELDS: [string, string, string][] = [
  ["venue", "Venue", "Only filled facts are ever shared. Empty = unknown, and questions are sent to a person."],
  ["schedule", "Schedule", ""],
  ["reporting_time", "Reporting time", ""],
  ["submission_deadline", "Submission deadline", ""],
];

function EventForm({ initial, onSaved }: { initial?: EventInfo; onSaved: () => void }) {
  const { reload, select } = useEvent();
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [contact, setContact] = useState(initial?.organizer_contact ?? "");
  const [info, setInfo] = useState<Record<string, string>>(initial?.approved_info ?? {});
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const body = { name: name.trim(), description, organizer_contact: contact || null, approved_info: info };
      const saved = initial ? await api.updateEvent(initial.id, body) : await api.createEvent(body);
      await reload(); if (!initial) select(saved.id); onSaved();
    } catch (ex) { setErr((ex as Error).message); } finally { setBusy(false); }
  }
  return (
    <form onSubmit={save} className="max-w-xl space-y-4">
      <Field label="Event name"><input required minLength={2} className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Description (optional)"><input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      <Field label="Organiser contact reference (optional)"><input className={inputCls} value={contact} onChange={(e) => setContact(e.target.value)} /></Field>
      <fieldset className="space-y-3 rounded-lg border border-line bg-canvas/50 p-4">
        <legend className="px-1 text-xs font-semibold text-ink-2">Approved event information</legend>
        <p className="text-xs text-muted">Enter only facts you have verified. Cadence never guesses: if a participant asks about something left blank, the request goes to your follow-up queue.</p>
        {INFO_FIELDS.map(([k, label]) => (
          <Field key={k} label={label}><input className={inputCls} value={info[k] ?? ""} onChange={(e) => setInfo({ ...info, [k]: e.target.value })} /></Field>
        ))}
      </fieldset>
      {err && <p role="alert" className="drop-in text-sm font-medium text-bad">{err}</p>}
      <Button type="submit" disabled={busy}>{initial ? "Save changes" : "Create event"}</Button>
    </form>
  );
}

export default function EventsPage() {
  const { events, selected, select } = useEvent();
  const [editing, setEditing] = useState<number | "new" | null>(null);
  return (
    <>
      <PageHeader title="Events" subtitle="An event holds the approved facts that calls may relay. Campaigns always belong to one event."
        actions={<Button onClick={() => setEditing("new")}>New event</Button>} />
      <div className="space-y-4">
        {editing === "new" && <Card title="New event"><EventForm onSaved={() => setEditing(null)} /></Card>}
        {events.map((e) => (
          <Card key={e.id} title={e.name} action={<div className="flex gap-2">
            {e.is_demo && <Badge tone="warn">Sample</Badge>}
            {selected?.id === e.id ? <Badge tone="good">Selected</Badge> : <Button variant="secondary" onClick={() => select(e.id)}>Select</Button>}
            <Button variant="secondary" onClick={() => setEditing(editing === e.id ? null : e.id)}>{editing === e.id ? "Close" : "Edit"}</Button></div>}>
            {editing === e.id ? <EventForm initial={e} onSaved={() => setEditing(null)} /> : (
              <dl className="grid grid-cols-[10rem_1fr] gap-y-1 text-sm">
                <dt className="text-muted">Campaigns</dt><dd>{e.campaign_count}</dd>
                {INFO_FIELDS.map(([k, label]) => (<Fragment key={k}><dt className="text-muted">{label}</dt><dd>{e.approved_info[k] ?? <span className="text-muted">not configured</span>}</dd></Fragment>))}
                {e.description && <><dt className="text-muted">Description</dt><dd>{e.description}</dd></>}
              </dl>
            )}
          </Card>
        ))}
        {events.length === 0 && editing !== "new" && <Card><p className="text-sm text-muted">No events yet. Create one, or load the sample from the Dashboard.</p></Card>}
      </div>
    </>
  );
}
