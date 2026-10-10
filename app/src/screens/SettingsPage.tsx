import { Text, View } from "react-native";
import { useRouter } from "expo-router";
import { ChevronRight } from "lucide-react-native";
import { API_BASE, api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { Badge, Card, ErrorState, Hero, Loading, Row, Screen, type } from "../components/ui";
import { fonts } from "../theme";

export default function SettingsPage() {
  const router = useRouter();
  const settings = useAsync(() => api.settings(), []);
  const exotel = useAsync(() => api.exotelReadiness(), []);
  const s = settings.data;
  return (
    <Screen onRefresh={() => { settings.reload(); exotel.reload(); }} refreshing={settings.loading || exotel.loading}>
      <Hero title="More" subtitle="Events, analytics and how Cadence is calling." />
      <Card>
        {([["Events", "/events"], ["Analytics", "/analytics"]] as const).map(([l, to], n) => (
          <Row key={to} last={n === 1} onPress={() => router.push(to)}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 32 }}>
              <Text style={[type.body, { fontFamily: fonts.bold }]}>{l}</Text><ChevronRight size={18} color="#55695b" />
            </View>
          </Row>))}
      </Card>

      {settings.loading && !s && <Loading />}
      {settings.error && <ErrorState error={settings.error} retry={settings.reload} />}
      {s && (<>
        <Card title="Calling">
          <View style={{ gap: 10 }}>
            <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
              <Text style={type.body}>Provider</Text>
              <Badge tone={s.provider === "demo" ? "warn" : "good"}>{s.provider === "demo" ? "Demo: calls simulated" : s.provider}</Badge>
            </View>
            <Text style={type.small}>Retries: up to {s.retry_policy.max_attempts_default} attempts, {s.retry_policy.backoff_minutes} min apart, on {s.retry_policy.retry_on.join(", ")}.</Text>
            <Text style={type.small}>Transcription: {s.transcription}</Text>
            <Text style={type.small}>Data: {s.data_location}</Text>
            <Text style={type.small}>Backend: {API_BASE}</Text>
          </View>
        </Card>
        <Card title="Languages">
          {s.languages.map((l, n) => (
            <Row key={l.code} last={n === s.languages.length - 1}>
              <Text style={[type.body, { fontFamily: fonts.bold }]}>{l.name}</Text><Text style={type.small}>{l.support}</Text>
            </Row>))}
        </Card>
      </>)}

      {exotel.error ? <ErrorState error={exotel.error} retry={exotel.reload} /> : exotel.data ? (
        <Card title="Exotel readiness" action={<Badge tone={exotel.data.ready ? "good" : "warn"}>{exotel.data.ready ? "Ready" : "Not ready"}</Badge>}>
          {exotel.data.checks.map((c, n) => (
            <Row key={c.name} last={n === exotel.data!.checks.length - 1}>
              <View style={{ flexDirection: "row", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <Badge tone={c.ok ? "good" : c.required ? "bad" : "neutral"}>{c.ok ? "OK" : c.required ? "Missing" : "Optional"}</Badge>
                <Text style={type.body}>{c.name}</Text>
              </View>
              {c.detail ? <Text style={type.small}>{c.detail}</Text> : null}
            </Row>))}
          <Text style={[type.small, { marginTop: 10 }]}>{exotel.data.note}</Text>
        </Card>
      ) : null}
    </Screen>
  );
}
