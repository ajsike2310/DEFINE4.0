import { useState } from "react";
import { Alert, Platform, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { Badge, Button, Card, Empty, ErrorState, Hero, Loading, Row, Screen, SimBadge, type } from "../components/ui";
import { CAMPAIGN_LABEL, CAMPAIGN_TONE, LANG_LABEL, OUTCOME_LABEL, OUTCOME_TONE, PURPOSE_LABEL, fmtDate, maskPhone } from "../services/labels";
import { fonts } from "../theme";

/** Destructive actions ask first. Alert.alert has no buttons on web, so web uses confirm(). */
function confirmAction(title: string, message: string, ok: string): Promise<boolean> {
  if (Platform.OS === "web") return Promise.resolve(typeof window !== "undefined" && window.confirm(`${title}\n\n${message}`));
  return new Promise((resolve) => Alert.alert(title, message, [{ text: "Keep it", style: "cancel", onPress: () => resolve(false) }, { text: ok, style: "destructive", onPress: () => resolve(true) }]));
}

export default function CampaignDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const cid = Number(id);
  const router = useRouter();
  const camp = useAsync(() => api.campaign(cid), [cid]);
  const recips = useAsync(() => api.recipients(cid), [cid]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [fail, setFail] = useState<string | null>(null);
  const c = camp.data;

  async function act(fn: () => Promise<unknown>, done: (r: never) => string) {
    setBusy(true); setFail(null); setNote(null);
    try { const r = await fn(); setNote(done(r as never)); camp.reload(); recips.reload(); }
    catch (e) { setFail((e as Error).message); }
    finally { setBusy(false); }
  }
  async function cancel() {
    if (await confirmAction("Cancel this campaign?", "No further calls will be placed. Results so far are kept.", "Cancel campaign"))
      void act(() => api.cancelCampaign(cid), () => "Campaign cancelled.");
  }

  return (
    <Screen onRefresh={() => { camp.reload(); recips.reload(); }} refreshing={camp.loading || recips.loading}>
      <View style={{ alignSelf: "flex-start" }}><Button title="‹ All campaigns" variant="secondary" onPress={() => router.replace("/campaigns")} /></View>
      {camp.loading && !c && <Loading />}
      {camp.error && <ErrorState error={camp.error} retry={camp.reload} />}
      {c && (<>
        <Hero title={c.name} subtitle={`${PURPOSE_LABEL[c.purpose] ?? c.purpose} · ${c.recipient_count} participants`}>
          <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
            <Badge tone={CAMPAIGN_TONE[c.status]}>{CAMPAIGN_LABEL[c.status] ?? c.status}</Badge><SimBadge simulated={c.is_demo} />
            {c.scheduled_at ? <Badge tone="info">Starts {fmtDate(c.scheduled_at)}</Badge> : null}
          </View>
          <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap", marginTop: 16 }}>
            {(c.status === "draft" || c.status === "scheduled") ? <Button title="Start now" busy={busy} disabled={c.recipient_count === 0}
              onPress={() => act(() => api.startCampaign(c.id), (r: { dispatched: number; skipped: unknown[] }) => `${r.dispatched} call(s) dispatched, ${r.skipped.length} skipped.`)} /> : null}
            {c.status === "running" ? <Button title={c.is_demo ? "Run retries now" : "Run due retries"} variant="secondary" busy={busy}
              onPress={() => act(() => api.retryDue(c.id, c.is_demo), (r: { dispatched: number }) => `${r.dispatched} retry call(s) placed.`)} /> : null}
            {["draft", "scheduled", "running"].includes(c.status) ? <Button title="Cancel" variant="danger" disabled={busy} onPress={() => void cancel()} /> : null}
          </View>
        </Hero>
        {note ? <Card><Text accessibilityRole="alert" style={type.body}>{note}</Text></Card> : null}
        {fail ? <ErrorState error={new Error(fail)} /> : null}

        <Card title="Messages">
          {c.languages.map((l, n) => (
            <View key={l} style={{ gap: 6, marginBottom: n < c.languages.length - 1 ? 16 : 0 }}>
              <Text style={type.label}>{LANG_LABEL[l] ?? l}</Text>
              <Text style={l === "ml" ? type.ml : type.body}>{c.messages[l]}</Text>
            </View>))}
          <Text style={[type.small, { marginTop: 12 }]}>Up to {c.max_attempts} attempts per participant · consent {c.require_consent ? "required" : "not required"}</Text>
        </Card>

        <Card title="Participants">
          {recips.loading && !recips.data ? <Loading /> : recips.error ? <ErrorState error={recips.error} retry={recips.reload} />
            : !recips.data?.length ? <Empty title="No participants yet" body="Import a CSV when creating the campaign, or add people from the web app." />
            : recips.data.map((r, n, arr) => (
              <Row key={r.id} last={n === arr.length - 1}>
                <Text style={[type.body, { fontFamily: fonts.bold }]}>{r.name}</Text>
                <Text style={type.small}>{maskPhone(r.phone)} · consent {r.consent_status}</Text>
                <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
                  <Badge tone={OUTCOME_TONE[r.outcome]}>{OUTCOME_LABEL[r.outcome] ?? r.outcome}</Badge>
                  {r.opted_out ? <Badge tone="bad">Opted out</Badge> : null}
                </View>
              </Row>))}
        </Card>
      </>)}
    </Screen>
  );
}
