import { useState, type ReactNode } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View, type StyleProp, type TextInputProps, type ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { AlertTriangle, Inbox } from "lucide-react-native";
import { colors, fonts, radius, space, toneColor } from "../theme";
import type { Tone } from "../services/labels";

export const type = StyleSheet.create({
  display: { fontFamily: fonts.display, fontSize: 28, lineHeight: 31, letterSpacing: -0.6, color: colors.ink },
  title: { fontFamily: fonts.displayBold, fontSize: 18, lineHeight: 22, letterSpacing: -0.2, color: colors.ink },
  body: { fontFamily: fonts.body, fontSize: 14.5, lineHeight: 21, color: colors.ink },
  small: { fontFamily: fonts.body, fontSize: 12.5, lineHeight: 18, color: colors.muted },
  label: { fontFamily: fonts.semi, fontSize: 12.5, lineHeight: 16, color: colors.ink2 },
  /** Malayalam needs extra line height so tall glyphs are never clipped. */
  ml: { fontFamily: fonts.ml, fontSize: 15, lineHeight: 26, color: colors.ink },
});

export function Screen({ children, onRefresh, refreshing = false }: { children: ReactNode; onRefresh?: () => void; refreshing?: boolean }) {
  return (
    <SafeAreaView edges={["left", "right"]} style={s.screen}>
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled"
        refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} /> : undefined}>
        <View style={s.column}>{children}</View>
      </ScrollView>
    </SafeAreaView>
  );
}

/** The header block every screen opens with. */
export function Hero({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <View style={s.hero}>
      <Text style={type.display} accessibilityRole="header">{title}</Text>
      {subtitle ? <Text style={[type.small, { marginTop: 6 }]}>{subtitle}</Text> : null}
      {children ? <View style={{ marginTop: space.lg }}>{children}</View> : null}
    </View>
  );
}

export function Card({ title, action, children, tone }: { title?: string; action?: ReactNode; children: ReactNode; tone?: "signal" }) {
  return (
    <View style={[s.card, tone === "signal" && { borderColor: colors.signal, borderWidth: 2 }]}>
      {title ? <View style={s.cardHead}><Text style={type.title}>{title}</Text>{action}</View> : null}
      <View style={{ padding: space.lg }}>{children}</View>
    </View>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return <View style={{ gap: space.md }}><Text style={type.title}>{title}</Text>{children}</View>;
}

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  const c = toneColor[tone];
  return (
    <View style={[s.badge, { borderColor: c + "55", backgroundColor: c + "14" }]}>
      <View style={[s.dot, { backgroundColor: c }]} />
      <Text style={{ fontFamily: fonts.semi, fontSize: 11.5, color: c }}>{children}</Text>
    </View>
  );
}

export function SimBadge({ simulated }: { simulated: boolean }) {
  return simulated ? <Badge tone="warn">Simulated</Badge> : <Badge tone="good">Real</Badge>;
}

export function Stat({ label, value, hint, accent, onPress }: { label: string; value: ReactNode; hint?: string; accent?: boolean; onPress?: () => void }) {
  const body = (
    <View style={[s.stat, accent && { borderColor: colors.signal + "66", backgroundColor: colors.signalSoft + "88" }]}>
      <Text style={[type.small, { fontFamily: fonts.medium }]}>{label}</Text>
      <Text style={{ fontFamily: fonts.display, fontSize: 34, lineHeight: 38, color: accent ? colors.signal : colors.ink, marginTop: 4 }}>{value}</Text>
      {hint ? <Text style={[type.small, { marginTop: 4 }]}>{hint}</Text> : null}
    </View>
  );
  return onPress ? <Pressable onPress={onPress} accessibilityRole="button" style={{ flex: 1, minWidth: 150 }}>{body}</Pressable> : <View style={{ flex: 1, minWidth: 150 }}>{body}</View>;
}
export function StatRow({ children }: { children: ReactNode }) { return <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space.md }}>{children}</View>; }

export function Button({ title, onPress, variant = "primary", disabled, busy, icon }: { title: string; onPress?: () => void; variant?: "primary" | "secondary" | "danger"; disabled?: boolean; busy?: boolean; icon?: ReactNode }) {
  const v = { primary: { bg: colors.ink, fg: "#ffffff", bd: colors.ink }, secondary: { bg: colors.surface, fg: colors.ink, bd: colors.line }, danger: { bg: colors.surface, fg: colors.bad, bd: colors.bad + "66" } }[variant];
  const off = disabled || busy;
  return (
    <Pressable onPress={off ? undefined : onPress} accessibilityRole="button" accessibilityState={{ disabled: !!off, busy: !!busy }}
      style={({ pressed }) => [s.btn, { backgroundColor: v.bg, borderColor: v.bd, opacity: off ? 0.45 : 1, transform: [{ scale: pressed ? 0.98 : 1 }] }]}>
      {busy ? <ActivityIndicator size="small" color={v.fg} /> : icon}
      <Text style={{ fontFamily: fonts.bold, fontSize: 14, color: v.fg }}>{busy ? "Working…" : title}</Text>
    </Pressable>
  );
}

export function Field({ label, error, hint, style, multiline, ...p }: TextInputProps & { label: string; error?: string; hint?: string; style?: StyleProp<ViewStyle> }) {
  const [focus, setFocus] = useState(false);
  return (
    <View style={[{ gap: 6 }, style]}>
      <Text style={type.label}>{label}</Text>
      <TextInput {...p} multiline={multiline} accessibilityLabel={label} placeholderTextColor={colors.muted}
        onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
        style={[s.input, multiline && { minHeight: 120, textAlignVertical: "top", lineHeight: 24 }, focus && { borderColor: colors.brand, borderWidth: 2 }, error ? { borderColor: colors.bad } : null]} />
      {error ? <Text accessibilityRole="alert" style={{ fontFamily: fonts.semi, fontSize: 12.5, color: colors.bad }}>{error}</Text> : hint ? <Text style={type.small}>{hint}</Text> : null}
    </View>
  );
}

/** Wrapping choice chips: single or multi select. */
export function Chips<T extends string>({ options, value, onChange, label }: { options: [T, string][]; value: T | T[]; onChange: (v: T) => void; label: string }) {
  const on = (k: T) => (Array.isArray(value) ? value.includes(k) : value === k);
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={label} style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
      {options.map(([k, l]) => (
        <Pressable key={k} onPress={() => onChange(k)} accessibilityRole="button" accessibilityState={{ selected: on(k) }}
          style={[s.chip, on(k) && { backgroundColor: colors.ink, borderColor: colors.ink }]}>
          <Text style={{ fontFamily: fonts.semi, fontSize: 13, color: on(k) ? "#fff" : colors.ink2 }}>{l}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function Loading() { return <View style={{ paddingVertical: 48 }} accessibilityRole="progressbar"><ActivityIndicator color={colors.brand} /></View>; }

export function ErrorState({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <View accessibilityRole="alert" style={[s.card, { borderColor: colors.bad + "66", padding: space.lg, gap: 8, flexDirection: "row" }]}>
      <AlertTriangle size={18} color={colors.bad} />
      <View style={{ flex: 1, gap: 4 }}>
        <Text style={[type.body, { fontFamily: fonts.bold, color: colors.bad }]}>Could not load this</Text>
        <Text style={type.small}>{error.message}</Text>
        {retry ? <View style={{ alignSelf: "flex-start", marginTop: 6 }}><Button title="Retry" variant="secondary" onPress={retry} /></View> : null}
      </View>
    </View>
  );
}

export function Empty({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <View style={{ alignItems: "center", gap: 8, paddingVertical: 40, paddingHorizontal: 12 }}>
      <View style={s.emptyIcon}><Inbox size={20} color={colors.marigoldInk} /></View>
      <Text style={type.title}>{title}</Text>
      <Text style={[type.small, { textAlign: "center", maxWidth: 320 }]}>{body}</Text>
      {action}
    </View>
  );
}

export function Row({ children, onPress, last }: { children: ReactNode; onPress?: () => void; last?: boolean }) {
  const inner = <View style={[s.row, !last && { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.line }]}>{children}</View>;
  return onPress ? <Pressable onPress={onPress} accessibilityRole="button">{inner}</Pressable> : inner;
}

/** Hatched / filled meter. value 0..1 or null. */
export function Meter({ label, value, color = colors.good }: { label: string; value: number | null; color?: string }) {
  return (
    <View style={{ gap: 6 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={type.body}>{label}</Text>
        <Text style={[type.body, { fontFamily: fonts.bold }]}>{value == null ? "—" : `${Math.round(value * 100)}%`}</Text>
      </View>
      <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.lineSoft, overflow: "hidden" }}>
        <View style={{ height: 8, width: `${Math.min(value ?? 0, 1) * 100}%`, backgroundColor: color, borderRadius: 4 }} />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.canvas },
  scroll: { padding: space.lg, paddingBottom: 48, alignItems: "center" },
  column: { width: "100%", maxWidth: 880, gap: space.xl },
  hero: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.line, padding: space.xl },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.line, overflow: "hidden" },
  cardHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: space.lg, paddingVertical: space.md, borderBottomWidth: 1, borderBottomColor: colors.lineSoft },
  badge: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2, alignSelf: "flex-start" },
  dot: { width: 6, height: 6, borderRadius: 3 },
  stat: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.line, padding: space.lg },
  btn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, minHeight: 44, paddingHorizontal: 18, borderRadius: radius.md, borderWidth: 1 },
  input: { minHeight: 44, borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, backgroundColor: colors.surface, paddingHorizontal: 12, paddingVertical: 10, fontFamily: fonts.body, fontSize: 15, color: colors.ink },
  chip: { minHeight: 40, justifyContent: "center", paddingHorizontal: 14, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface },
  emptyIcon: { width: 48, height: 48, borderRadius: 24, borderWidth: 2, borderStyle: "dashed", borderColor: colors.marigold, backgroundColor: colors.marigoldSoft, alignItems: "center", justifyContent: "center" },
  row: { paddingVertical: space.md, gap: 4 },
});
