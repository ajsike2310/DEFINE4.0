import { useState } from "react";
import { Text, View } from "react-native";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { Button, Card, ErrorState, Hero, Loading, Meter, Screen, Stat, StatRow, type } from "../components/ui";
import { NoEvent } from "../components/NoEvent";
import { GROUPS, Legend, OutcomeBar, ringsFrom } from "../components/Outcomes";
import { LANG_LABEL, pct } from "../services/labels";
import { colors, fonts } from "../theme";

export default function AnalyticsPage() {
  const { selected } = useEvent();
  const [source, setSource] = useState<"all" | "real" | "simulated">("all");
  const { data: a, error, loading, reload } = useAsync(() => (selected ? api.analytics({ eventId: selected.id, source }) : Promise.resolve(null)), [selected?.id, source]);
  const rings = a ? ringsFrom(a.outcomes) : [];
  return (
    <Screen onRefresh={reload} refreshing={loading}>
      <Hero title="Analytics" subtitle="Rates use documented denominators. Real and simulated calls can be separated." />
      <NoEvent />
      {selected && (<>
        <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
          {([["all", "All calls"], ["real", "Real only"], ["simulated", "Simulated only"]] as const).map(([k, l]) => <Button key={k} title={l} variant={source === k ? "primary" : "secondary"} onPress={() => setSource(k)} />)}
        </View>
        {loading && !a && <Loading />}
        {error && <ErrorState error={error} retry={reload} />}
        {a && (<>
          <Card title="Outcomes">
            <View style={{ gap: 14 }}>
              <OutcomeBar rings={rings} />
              <View><Legend rings={rings.map((r) => ({ ...r }))} /></View>
            </View>
          </Card>
          <StatRow>
            <Stat label="Participants" value={a.totals.recipients} hint={`${a.totals.recipients_contacted} contacted`} />
            <Stat label="Calls attempted" value={a.totals.calls_attempted} hint={`${a.totals.retries} retries`} />
            <Stat label="Answered" value={a.totals.calls_answered} hint={`${pct(a.rates.answer_rate)} of finished calls`} />
          </StatRow>
          <Card title="Rates">
            <View style={{ gap: 14 }}>
              <Meter label="Answer rate" value={a.rates.answer_rate ?? null} />
              <Meter label="Confirmation rate" value={a.rates.confirmation_rate ?? null} />
              {a.headcount ? <Meter label="Certainty of headcount range" value={a.headcount.certainty} color={colors.marigold} /> : null}
            </View>
          </Card>
          <Card title="By participant language">
            <View style={{ gap: 14 }}>
              {a.by_language.map((r) => {
                const total = GROUPS.reduce((n, g) => n + g.members.reduce((m, k) => m + (Number(r[k]) || 0), 0), 0) || 1;
                return (
                  <View key={r.language} style={{ gap: 6 }}>
                    <Text style={[type.body, { fontFamily: fonts.bold }]}>{LANG_LABEL[r.language] ?? r.language} <Text style={type.small}>· {r.recipients} participants</Text></Text>
                    <View style={{ flexDirection: "row", height: 12, borderRadius: 6, overflow: "hidden", backgroundColor: colors.lineSoft }} accessibilityLabel={`Outcomes for ${LANG_LABEL[r.language] ?? r.language}`}>
                      {GROUPS.map((g) => { const n = g.members.reduce((m, k) => m + (Number(r[k]) || 0), 0); return n ? <View key={g.key} style={{ width: `${(n / total) * 100}%`, backgroundColor: g.color }} /> : null; })}
                    </View>
                  </View>);
              })}
            </View>
          </Card>
        </>)}
      </>)}
    </Screen>
  );
}
