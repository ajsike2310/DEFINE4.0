import { useState } from "react";
import { Text, View } from "react-native";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { Badge, Card, Chips, Empty, ErrorState, Hero, Loading, Row, Screen, type } from "../components/ui";
import { NoEvent } from "../components/NoEvent";
import { LANG_LABEL, OUTCOME_LABEL, OUTCOME_TONE, maskPhone } from "../services/labels";
import { fonts } from "../theme";

const FILTERS: [string, string][] = [["all", "All"], ["attention", "Needs attention"], ["retry", "Retry eligible"], ["callback", "Callback"], ["optout", "Opted out"]];

export default function Participants() {
  const { selected } = useEvent();
  const [filter, setFilter] = useState("all");
  const { data, error, loading, reload } = useAsync(() => (selected ? api.participants({ eventId: selected.id, filter }) : Promise.resolve([])), [selected?.id, filter]);
  return (
    <Screen onRefresh={reload} refreshing={loading}>
      <Hero title="Participants" subtitle="Phone numbers are masked. Consent and opt-out are shown for every person." />
      <NoEvent />
      {selected && (<>
        <Chips label="Filter participants" options={FILTERS} value={filter} onChange={setFilter} />
        {loading && !data && <Loading />}
        {error && <ErrorState error={error} retry={reload} />}
        {data && (
          <Card>
            {data.length === 0 ? <Empty title="No participants match" body="Try another filter, or add participants to a campaign." /> : data.map((r, n) => (
              <Row key={r.id} last={n === data.length - 1}>
                <Text style={[type.body, { fontFamily: fonts.bold }]}>{r.name}{r.external_ref ? <Text style={type.small}>  {r.external_ref}</Text> : null}</Text>
                <Text style={type.small}>{maskPhone(r.phone)} · {LANG_LABEL[r.preferred_language ?? "unspecified"] ?? r.preferred_language} · consent {r.consent_status}</Text>
                <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
                  <Badge tone={OUTCOME_TONE[r.outcome]}>{OUTCOME_LABEL[r.outcome] ?? r.outcome}</Badge>
                  {r.opted_out ? <Badge tone="bad">Opted out</Badge> : null}
                  {r.is_demo ? <Badge tone="warn">Simulated</Badge> : null}
                </View>
              </Row>))}
          </Card>
        )}
      </>)}
    </Screen>
  );
}
