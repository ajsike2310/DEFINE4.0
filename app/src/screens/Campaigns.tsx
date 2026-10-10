import { Text, View } from "react-native";
import { useRouter } from "expo-router";
import { Plus } from "lucide-react-native";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { Badge, Button, Card, Empty, ErrorState, Hero, Loading, Row, Screen, SimBadge, type } from "../components/ui";
import { NoEvent } from "../components/NoEvent";
import { CAMPAIGN_LABEL, CAMPAIGN_TONE, PURPOSE_LABEL } from "../services/labels";
import { colors, fonts } from "../theme";

export default function Campaigns() {
  const { selected } = useEvent();
  const router = useRouter();
  const { data, error, loading, reload } = useAsync(() => (selected ? api.campaigns(selected.id) : Promise.resolve([])), [selected?.id]);
  return (
    <Screen onRefresh={reload} refreshing={loading}>
      <Hero title="Campaigns" subtitle={selected ? `Every campaign for ${selected.name}.` : undefined}>
        {selected ? <View style={{ alignSelf: "flex-start" }}><Button title="New campaign" icon={<Plus size={16} color="#ffffff" />} onPress={() => router.push("/campaigns/new")} /></View> : null}
      </Hero>
      <NoEvent />
      {selected && (<>
        {loading && !data && <Loading />}
        {error && <ErrorState error={error} retry={reload} />}
        {data && (
          <Card>
            {data.length === 0 ? <Empty title="No campaigns yet" body="Create an attendance confirmation campaign to start." /> : data.map((c, n) => (
              <Row key={c.id} last={n === data.length - 1} onPress={() => router.push(`/campaigns/${c.id}`)}>
                <Text style={[type.body, { fontFamily: fonts.bold }]}>{c.name}</Text>
                <Text style={type.small}>{PURPOSE_LABEL[c.purpose] ?? c.purpose} · {c.recipient_count} participants · {c.languages.join(", ")}</Text>
                <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
                  <Badge tone={CAMPAIGN_TONE[c.status]}>{CAMPAIGN_LABEL[c.status] ?? c.status}</Badge>
                  <SimBadge simulated={c.is_demo} />
                </View>
              </Row>))}
          </Card>
        )}
      </>)}
    </Screen>
  );
}
