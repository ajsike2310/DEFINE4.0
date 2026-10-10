import { Text, View } from "react-native";
import { colors, fonts } from "../theme";

export interface OutcomeRing { key: string; label: string; count: number; color: string }

export const GROUPS: { key: string; label: string; members: string[]; color: string }[] = [
  { key: "attending", label: "Attending", members: ["confirmed"], color: colors.good },
  { key: "acknowledged", label: "Acknowledged", members: ["acknowledged"], color: colors.marigold },
  { key: "open", label: "Callback or info requested", members: ["callback_requested", "information_requested"], color: colors.thumbi },
  { key: "human", label: "Needs human", members: ["unclear", "human_required"], color: colors.signal },
  { key: "declined", label: "Declined or opted out", members: ["declined", "opted_out"], color: colors.bad },
  { key: "none", label: "Not reached", members: ["no_response"], color: colors.sage },
];

export function ringsFrom(outcomes: Record<string, number>): OutcomeRing[] {
  return GROUPS.map((g) => ({ key: g.key, label: g.label, color: g.color, count: g.members.reduce((n, m) => n + (outcomes[m] ?? 0), 0) }));
}

/** One flat stacked bar of the outcome split. The legend beside it carries the numbers. */
export function OutcomeBar({ rings }: { rings: OutcomeRing[] }) {
  return (
    <View style={{ flexDirection: "row", height: 10, borderRadius: 5, overflow: "hidden", backgroundColor: colors.lineSoft }} accessibilityLabel={`Outcome split: ${rings.map((r) => `${r.label} ${r.count}`).join(", ")}`}>
      {rings.map((r) => (r.count ? <View key={r.key} style={{ flex: r.count, backgroundColor: r.color }} /> : null))}
    </View>
  );
}

export function Legend({ rings, onDark = false }: { rings: OutcomeRing[]; onDark?: boolean }) {
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", columnGap: 16, rowGap: 6 }}>
      {rings.map((r) => (
        <View key={r.key} style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: r.color }} />
          <Text style={{ fontFamily: fonts.body, fontSize: 12.5, color: onDark ? colors.muted : colors.ink2 }}>{r.label} <Text style={{ fontFamily: fonts.bold, color: onDark ? "#fff" : colors.ink }}>{r.count}</Text></Text>
        </View>
      ))}
    </View>
  );
}
