import { useState } from "react";
import { Text, View } from "react-native";
import { api, ApiError } from "../services/api";
import { useEvent } from "../hooks/useEvent";
import { Badge, Button, Card, Empty, ErrorState, Field, Hero, Loading, Row, Screen, type } from "../components/ui";
import { fonts } from "../theme";

export default function EventsPage() {
  const { events, selected, select, loading, error, reload } = useEvent();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [contact, setContact] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [fieldErr, setFieldErr] = useState<string | undefined>();

  async function create() {
    if (name.trim().length < 2) { setFieldErr("Enter an event name (at least 2 characters)."); return; }
    setBusy(true); setErr(null); setFieldErr(undefined);
    try {
      const e = await api.createEvent({ name: name.trim(), description: description.trim(), approved_info: {}, organizer_contact: contact.trim() || null });
      await reload(); select(e.id); setName(""); setDescription(""); setContact("");
    } catch (e) { setErr(e instanceof ApiError && e.details ? e.details.map((d) => `${d.field}: ${d.message}`).join(" · ") : (e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <Screen onRefresh={() => void reload()} refreshing={loading}>
      <Hero title="Events" subtitle="Each event has its own campaigns, participants and approved information." />
      {loading && !events.length && <Loading />}
      {error && <ErrorState error={error} retry={() => void reload()} />}
      <Card title="Your events">
        {events.length === 0 ? <Empty title="No events yet" body="Create your first event below." /> : events.map((e, n) => (
          <Row key={e.id} last={n === events.length - 1} onPress={() => select(e.id)}>
            <Text style={[type.body, { fontFamily: fonts.bold }]}>{e.name}</Text>
            {e.description ? <Text style={type.small}>{e.description}</Text> : null}
            <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
              <Badge tone="neutral">{e.campaign_count} campaign{e.campaign_count === 1 ? "" : "s"}</Badge>
              {e.is_demo ? <Badge tone="warn">Sample</Badge> : null}
              {e.id === selected?.id ? <Badge tone="good">Selected</Badge> : null}
            </View>
          </Row>))}
      </Card>
      <Card title="New event">
        <View style={{ gap: 14 }}>
          <Field label="Event name" value={name} onChangeText={setName} error={fieldErr} />
          <Field label="Description (optional)" value={description} onChangeText={setDescription} multiline />
          <Field label="Organiser contact (optional)" value={contact} onChangeText={setContact} autoCapitalize="none" />
          {err ? <ErrorState error={new Error(err)} /> : null}
          <View style={{ alignSelf: "flex-start" }}><Button title="Create event" busy={busy} onPress={() => void create()} /></View>
        </View>
      </Card>
    </Screen>
  );
}
