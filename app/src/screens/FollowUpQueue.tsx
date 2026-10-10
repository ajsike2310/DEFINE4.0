import { useState } from "react";
import { Alert, Pressable, Text, View } from "react-native";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { Badge, Button, Card, Empty, ErrorState, Hero, Loading, Screen, SimBadge, type } from "../components/ui";
import { NoEvent } from "../components/NoEvent";
import { OUTCOME_LABEL, fmtDate, maskPhone } from "../services/labels";
import { fonts } from "../theme";

const PRIO: Record<number, { label: string; tone: "bad" | "warn" | "info" }> = {
  1: { label: "P1 Due now", tone: "bad" }, 2: { label: "P2 Needs a person", tone: "warn" }, 3: { label: "P3 Info to relay", tone: "info" },
};

export default function FollowUpQueue() {
  const { selected } = useEvent();
  const { data, error, loading, reload } = useAsync(() => (selected ? api.followupQueue({ eventId: selected.id }) : Promise.resolve([])), [selected?.id]);
  const [busy, setBusy] = useState<number | null>(null);
  const [shown, setShown] = useState<number[]>([]);   // numbers revealed in full; masked by default

  async function run(id: number, fn: () => Promise<unknown>, done?: string) {
    setBusy(id);
    try { await fn(); if (done) Alert.alert(done); reload(); }
    catch (e) { Alert.alert("That did not work", (e as Error).message); }
    finally { setBusy(null); }
  }
  const clarify = (id: number, rid: number) => run(id, async () => {
    const r = await api.clarifyRecipient(rid);
    if (!r.dispatched) throw new Error(r.skipped[0]?.reason ?? "Not allowed for this participant.");
  }, "Clarification call placed");

  return (
    <Screen onRefresh={reload} refreshing={loading}>
      <Hero title="Follow-up queue" subtitle="Due callbacks first, then responses a person must resolve, then information to relay." />
      <NoEvent />
      {selected && (<>
        {loading && !data && <Loading />}
        {error && <ErrorState error={error} retry={reload} />}
        {data && (data.length === 0
          ? <Card><Empty title="Nothing to follow up" body="Callback requests, unclear answers and information requests will appear here after calls complete." /></Card>
          : data.map((i) => {
            const p = PRIO[i.priority] ?? PRIO[3];
            return (
              <Card key={i.followup_id}>
                <View style={{ gap: 8 }}>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                    <Badge tone={p.tone}>{p.label}</Badge><SimBadge simulated={i.is_simulated} />
                  </View>
                  <Text style={[type.title]}>{i.participant_name}{i.participant_ref ? <Text style={type.small}>  {i.participant_ref}</Text> : null}</Text>
                  {i.participant_phone ? (
                    <Pressable onPress={() => setShown((s) => (s.includes(i.followup_id) ? s.filter((x) => x !== i.followup_id) : [...s, i.followup_id]))}
                      accessibilityRole="button" accessibilityLabel={`${shown.includes(i.followup_id) ? "Hide" : "Show"} full number for ${i.participant_name}`}>
                      <Text style={type.body}>{shown.includes(i.followup_id) ? i.participant_phone : maskPhone(i.participant_phone)}  <Text style={type.small}>{shown.includes(i.followup_id) ? "Hide" : "Show"}</Text></Text>
                    </Pressable>
                  ) : null}
                  <Text style={type.body}>{i.reason}</Text>
                  <Text style={type.body}><Text style={{ fontFamily: fonts.bold }}>Next: </Text>{i.recommended_action}</Text>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
                    <Button title="Mark complete" busy={busy === i.followup_id} onPress={() => run(i.followup_id, () => api.patchFollowup(i.followup_id, { status: "completed" }))} />
                    {i.can_clarify && !i.clarification_attempted ? <Button title="Clarify call" variant="secondary" disabled={busy !== null} onPress={() => void clarify(i.followup_id, i.recipient_id)} /> : null}
                    <Button title="Dismiss" variant="secondary" disabled={busy !== null} onPress={() => run(i.followup_id, () => api.patchFollowup(i.followup_id, { status: "cancelled" }))} />
                  </View>
                </View>
              </Card>
            );
          }))}
      </>)}
    </Screen>
  );
}
