import { useRef, useState } from "react";
import { Platform, Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";
import * as DocumentPicker from "expo-document-picker";
import { Check } from "lucide-react-native";
import { ApiError, api, type FormDataValue } from "../services/api";
import { useEvent } from "../hooks/useEvent";
import { Button, Card, Chips, ErrorState, Field, Hero, Screen, type } from "../components/ui";
import { NoEvent } from "../components/NoEvent";
import { LANG_LABEL, PURPOSE_LABEL } from "../services/labels";
import { TEMPLATES } from "../services/templates";
import { colors, fonts } from "../theme";

const STEPS = ["Purpose", "Message", "People", "Review"];

export default function NewCampaign() {
  const router = useRouter();
  const { selected } = useEvent();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("attendance_confirmation");
  const [languages, setLanguages] = useState<string[]>(["en"]);
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [file, setFile] = useState<{ name: string; value: FormDataValue } | null>(null);
  const [consent, setConsent] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  // A partly finished submit is resumed on retry instead of creating a second campaign.
  const created = useRef<{ id: number; imported: boolean; notes: string[] } | null>(null);

  const evName = selected?.name ?? "the event";
  const msgFor = (l: string) => messages[l] ?? (l === "en" ? TEMPLATES[purpose].en(evName) : TEMPLATES[purpose].ml?.(evName) ?? "");

  function validate(s: number) {
    const e: Record<string, string> = {};
    if (s === 0 && name.trim().length < 2) e.name = "Enter a campaign name (at least 2 characters).";
    if (s === 0 && languages.length === 0) e.languages = "Select at least one language.";
    if (s === 1) languages.forEach((l) => {
      const m = msgFor(l).trim();
      if (!m) e[`msg_${l}`] = `Message required for ${LANG_LABEL[l]}.`;
      else if (m.includes("[ORGANISER")) e[`msg_${l}`] = "Replace the bracketed placeholder with details you have verified.";
    });
    if (s === 2 && file && !consent) e.consent = "Confirm you have consent to call these contacts, or remove the file.";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function pick() {
    const r = await DocumentPicker.getDocumentAsync({ type: ["text/csv", "text/comma-separated-values", "application/vnd.ms-excel", "text/plain"], copyToCacheDirectory: true });
    if (r.canceled || !r.assets[0]) return;
    const a = r.assets[0];
    setFile({ name: a.name, value: Platform.OS === "web" && a.file ? a.file : { uri: a.uri, name: a.name, type: a.mimeType ?? "text/csv" } });
  }

  async function submit(launch: boolean) {
    if (busy || !selected) return;
    if (!validate(1) || !validate(2)) return;
    setBusy(true); setResult(null);
    try {
      if (!created.current) {
        const c = await api.createCampaign({ event_id: selected.id, name: name.trim(), purpose, languages, max_attempts: maxAttempts, require_consent: true,
          messages: Object.fromEntries(languages.map((l) => [l, msgFor(l)])) });
        created.current = { id: c.id, imported: false, notes: [] };
      }
      const c = created.current;
      if (file && !c.imported) {
        const r = await api.importRecipients(c.id, file.value, consent);
        c.imported = true;
        c.notes.push(`${r.imported} imported${r.rejected ? `, ${r.rejected} rejected` : ""}`);
      }
      if (launch) {
        const r = await api.startCampaign(c.id);
        c.notes.push(`${r.dispatched} call(s) dispatched, ${r.skipped.length} skipped`);
      }
      router.replace(`/campaigns/${c.id}`);
    } catch (e) {
      const why = e instanceof ApiError && e.details ? e.details.map((d) => `${d.field}: ${d.message}`).join(" · ") : (e as Error).message;
      setResult(created.current ? `${why} The draft campaign was already saved; pressing the button again continues from where it stopped.` : why);
      setBusy(false);
    }
  }

  const toggleLang = (l: string) => setLanguages((ls) => (ls.includes(l) ? ls.filter((x) => x !== l) : [...ls, l]));

  return (
    <Screen>
      <View style={{ alignSelf: "flex-start" }}><Button title="‹ Back" variant="secondary" onPress={() => router.replace("/campaigns")} /></View>
      <Hero title="New campaign" subtitle={selected ? `For ${selected.name}. Saved as a draft unless you launch it.` : undefined} />
      <NoEvent />
      {selected && (<>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }} accessibilityLabel={`Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}`}>
          {STEPS.map((s, i) => (
            <View key={s} style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <View style={{ width: 26, height: 26, borderRadius: 13, alignItems: "center", justifyContent: "center", borderWidth: 1.5, borderColor: i <= step ? colors.ink : colors.line, backgroundColor: i < step ? colors.ink : colors.surface }}>
                {i < step ? <Check size={14} color="#fff" /> : <Text style={{ fontFamily: fonts.bold, fontSize: 12, color: i === step ? colors.ink : colors.muted }}>{i + 1}</Text>}
              </View>
              {i === step ? <Text style={type.label}>{s}</Text> : null}
              {i < STEPS.length - 1 ? <View style={{ width: 18, height: 2, backgroundColor: i < step ? colors.ink : colors.line }} /> : null}
            </View>))}
        </View>

        <Card>
          <View style={{ gap: 16 }}>
            {step === 0 && (<>
              <Field label="Campaign name" value={name} onChangeText={setName} error={errors.name} />
              <View style={{ gap: 6 }}><Text style={type.label}>Purpose</Text>
                <Chips label="Purpose" options={Object.entries(PURPOSE_LABEL) as [string, string][]} value={purpose} onChange={(v) => { setPurpose(v); setMessages({}); }} /></View>
              <View style={{ gap: 6 }}><Text style={type.label}>Languages</Text>
                <Chips label="Languages" options={[["en", "English"], ["ml", "Malayalam"]]} value={languages} onChange={toggleLang} />
                <Text style={type.small}>Malayalam understanding is rule-based and experimental.</Text>
                {errors.languages ? <Text accessibilityRole="alert" style={{ color: colors.bad, fontFamily: fonts.semi, fontSize: 12.5 }}>{errors.languages}</Text> : null}</View>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
                <Text style={[type.label, { flex: 1 }]}>Max call attempts per participant</Text>
                <Button title="−" variant="secondary" disabled={maxAttempts <= 1} onPress={() => setMaxAttempts((n) => Math.max(1, n - 1))} />
                <Text style={[type.title, { minWidth: 20, textAlign: "center" }]}>{maxAttempts}</Text>
                <Button title="+" variant="secondary" disabled={maxAttempts >= 5} onPress={() => setMaxAttempts((n) => Math.min(5, n + 1))} />
              </View>
            </>)}
            {step === 1 && languages.map((l) => (
              <Field key={l} label={`Message — ${LANG_LABEL[l]}`} multiline value={msgFor(l)} onChangeText={(t) => setMessages({ ...messages, [l]: t })}
                error={errors[`msg_${l}`]} hint={l === "ml" && !TEMPLATES[purpose].ml ? "No sample Malayalam text for this purpose; write or paste your reviewed message." : undefined}
                style={undefined} />))}
            {step === 2 && (<>
              <View style={{ gap: 8 }}>
                <Text style={type.label}>Import participants from CSV</Text>
                <Text style={type.small}>Columns: name, phone (E.164, e.g. +919876543210). Optional: participant_id, language, segment, opted_out.</Text>
                <View style={{ flexDirection: "row", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <Button title={file ? "Choose another file" : "Choose CSV file"} variant="secondary" onPress={() => void pick()} />
                  {file ? <><Text style={type.body}>{file.name}</Text><Button title="Remove" variant="secondary" onPress={() => { setFile(null); setConsent(false); }} /></> : null}
                </View>
              </View>
              <Pressable onPress={() => setConsent(!consent)} accessibilityRole="checkbox" accessibilityState={{ checked: consent }} style={{ flexDirection: "row", gap: 10, alignItems: "flex-start" }}>
                <View style={{ width: 24, height: 24, borderRadius: 6, borderWidth: 2, borderColor: colors.brand, backgroundColor: consent ? colors.brand : colors.surface, alignItems: "center", justifyContent: "center" }}>{consent ? <Check size={16} color="#fff" /> : null}</View>
                <Text style={[type.body, { flex: 1 }]}>I confirm these contacts are an authorised list and have agreed to receive calls of this kind.</Text>
              </Pressable>
              {errors.consent ? <Text accessibilityRole="alert" style={{ color: colors.bad, fontFamily: fonts.semi, fontSize: 12.5 }}>{errors.consent}</Text> : null}
              <Text style={type.small}>Without confirmed consent, participants are stored as unknown and skipped at launch. Reusing participants from another campaign is available on the web app.</Text>
            </>)}
            {step === 3 && (
              <View style={{ gap: 10 }}>
                {([["Event", selected.name], ["Name", name], ["Purpose", PURPOSE_LABEL[purpose]], ["Languages", languages.map((l) => LANG_LABEL[l]).join(", ")],
                  ["Attempts", `up to ${maxAttempts}`], ["Participants", file ? `${file.name} (consent ${consent ? "confirmed" : "not confirmed"})` : "none yet"],
                  ["Calling", selected.is_demo ? "Simulated (sample event)" : "Per backend provider setting"]] as [string, string][]).map(([k, v]) => (
                  <View key={k}><Text style={type.small}>{k}</Text><Text style={type.body}>{v}</Text></View>))}
              </View>)}
            {result ? <ErrorState error={new Error(result)} /> : null}
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              {step > 0 ? <Button title="Back" variant="secondary" disabled={busy} onPress={() => setStep(step - 1)} /> : null}
              {step < 3 ? <Button title="Continue" onPress={() => validate(step) && setStep(step + 1)} /> : (<>
                <Button title="Create draft" variant="secondary" busy={busy} onPress={() => void submit(false)} />
                <Button title="Create and launch now" busy={busy} disabled={!file} onPress={() => void submit(true)} />
              </>)}
            </View>
            {step === 3 && !file ? <Text style={type.small}>Launch is disabled until a participant file is added.</Text> : null}
          </View>
        </Card>
      </>)}
    </Screen>
  );
}
