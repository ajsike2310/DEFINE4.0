import { Text, View } from "react-native";
import { useRouter } from "expo-router";
import { Plus } from "lucide-react-native";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { Badge, Button, Card, Empty, ErrorState, Loading, Row, Screen, Stat, StatRow, type } from "../components/ui";
import { NoEvent } from "../components/NoEvent";
import { CAMPAIGN_LABEL, CAMPAIGN_TONE, PURPOSE_LABEL, pct } from "../services/labels";
import { colors, fonts } from "../theme";

/** Three questions, in order: who needs me, how many are coming, how are my campaigns doing.
 *  Outcome split, rates and language breakdowns live on the Analytics screen (More > Analytics). */
export default function Dashboard() {
  const { selected } = useEvent();
  const router = useRouter();
  const eid = selected?.id;
  const stats = useAsync(() => (eid ? api.analytics({ eventId: eid }) : Promise.resolve(null)), [eid]);
  const camps = useAsync(() => (eid ? api.campaigns(eid) : Promise.resolve([])), [eid]);
  const queue = useAsync(() => (eid ? api.followupQueue({ eventId: eid }) : Promise.resolve([])), [eid]);
  const a = stats.data;
  const refresh = () => { stats.reload(); camps.reload(); queue.reload(); };
  const h = a?.headcount;
  const items = queue.data ?? [];
  const awaiting = a ? Math.max(a.totals.recipients - a.outcomes.confirmed - a.outcomes.declined - a.outcomes.opted_out, 0) : 0;

  return (
    <Screen onRefresh={refresh} refreshing={stats.loading || camps.loading || queue.loading}>
      <NoEvent />
      {selected && (<>
        <View style={{ gap: 12 }}>
          <Text style={type.display} accessibilityRole="header">{selected.name}</Text>
          <View style={{ alignSelf: "flex-start" }}><Button title="New campaign" icon={<Plus size={16} color="#ffffff" />} onPress={() => router.push("/campaigns/new")} /></View>
        </View>

        {a ? (
          <StatRow>
            <Stat label="Total registered" value={a.totals.recipients} onPress={() => router.push("/participants")} />
            <Stat label="Accepted RSVP" value={a.outcomes.confirmed} hint={`${pct(a.rates.confirmation_rate)} of those who answered`} onPress={() => router.push("/participants")} />
            <Stat label="Declined" value={a.outcomes.declined + a.outcomes.opted_out} hint={`${a.outcomes.opted_out} opted out`} />
            <Stat label="Awaiting answer" value={awaiting} hint="No clear yes or no yet" onPress={() => router.push("/followups")} />
          </StatRow>
        ) : null}

        {queue.error ? <ErrorState error={queue.error} retry={queue.reload} /> : (
          <Card tone="signal" title={`Needs attention${items.length ? ` · ${items.length}` : ""}`}
            action={items.length ? <Button title="Open queue" onPress={() => router.push("/followups")} /> : undefined}>
            {items.length === 0 ? <Text style={type.body}>Nothing needs a person right now.</Text> : (
              <View>
                {items.slice(0, 3).map((i, n) => (
                  <Row key={i.followup_id} last={n === Math.min(items.length, 3) - 1}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <Text style={[type.body, { fontFamily: fonts.bold }]}>{i.participant_name}</Text>
                      <Badge tone={i.priority === 1 ? "bad" : i.priority === 2 ? "warn" : "info"}>{`P${i.priority}`}</Badge>
                    </View>
                    <Text style={type.small}>{i.recommended_action}</Text>
                  </Row>
                ))}
                {items.length > 3 ? <Text style={[type.small, { marginTop: 8 }]}>+{items.length - 3} more in the queue</Text> : null}
              </View>
            )}
          </Card>
        )}

        {stats.error ? <ErrorState error={stats.error} retry={stats.reload} /> : stats.loading && !a ? <Loading /> : null}
        {a ? (
          <Card title="Expected attending">
            {h ? (
              <View style={{ gap: 6 }}>
                <View style={{ flexDirection: "row", alignItems: "baseline", gap: 10 }}>
                  <Text style={{ fontFamily: fonts.display, fontSize: 48, lineHeight: 54, color: colors.ink, backgroundColor: colors.marigold, paddingHorizontal: 8, borderRadius: 6, overflow: "hidden" }}>{h.floor}</Text>
                  <Text style={{ fontFamily: fonts.medium, fontSize: 18, color: colors.muted }}>to</Text>
                  <Text style={{ fontFamily: fonts.display, fontSize: 48, lineHeight: 54, color: colors.ink }}>{h.ceiling}</Text>
                </View>
                <Text style={type.small}>of {h.participants} participants · {pct(h.certainty)} certain</Text>
                <Text style={[type.body, { marginTop: 8 }]}><Text style={{ fontFamily: fonts.bold }}>{a.totals.recipients_contacted} of {a.totals.recipients}</Text> reached</Text>
                {a.totals.simulated_calls > 0 ? <View style={{ alignSelf: "flex-start", marginTop: 4 }}><Badge tone="warn">Includes simulated calls</Badge></View> : null}
              </View>
            ) : <Text style={type.body}>Appears once an attendance campaign has participants.</Text>}
          </Card>
        ) : null}

        <Card title="Campaigns" action={<Button title="All" variant="secondary" onPress={() => router.push("/campaigns")} />}>
          {camps.error ? <ErrorState error={camps.error} retry={camps.reload} /> : !camps.data?.length
            ? <Empty title="No campaigns for this event" body="Create an attendance confirmation campaign to start." />
            : camps.data.slice(0, 5).map((c, n, arr) => (
              <Row key={c.id} last={n === arr.length - 1} onPress={() => router.push(`/campaigns/${c.id}`)}>
                <Text style={[type.body, { fontFamily: fonts.bold }]}>{c.name}</Text>
                <Text style={type.small}>{PURPOSE_LABEL[c.purpose] ?? c.purpose} · {c.recipient_count} participants</Text>
                <Badge tone={CAMPAIGN_TONE[c.status]}>{CAMPAIGN_LABEL[c.status] ?? c.status}</Badge>
              </Row>))}
        </Card>
      </>)}
    </Screen>
  );
}
