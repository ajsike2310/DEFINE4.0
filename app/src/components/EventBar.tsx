import { useState } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Svg, { Circle } from "react-native-svg";
import { Check, ChevronDown } from "lucide-react-native";
import { useEvent } from "../hooks/useEvent";
import { colors, fonts, radius, space } from "../theme";
import { type } from "./ui";

/** The brand mark: a small flower carpet of three rings. */
export function Mark({ size = 30 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 32 32">
      <Circle cx={16} cy={16} r={13} fill="none" stroke={colors.ink} strokeWidth={3.2} strokeDasharray={[62, 20]} strokeLinecap="round" rotation={-70} originX={16} originY={16} />
      <Circle cx={16} cy={16} r={7.6} fill="none" stroke={colors.signal} strokeWidth={3.2} strokeDasharray={[34, 14]} strokeLinecap="round" rotation={20} originX={16} originY={16} />
      <Circle cx={16} cy={16} r={2.6} fill={colors.marigold} stroke={colors.ink} strokeWidth={1} />
    </Svg>
  );
}

/** Top bar: brand, and the event every screen is scoped to. */
export function EventBar() {
  const { events, selected, select } = useEvent();
  const [open, setOpen] = useState(false);
  return (
    <SafeAreaView edges={["top", "left", "right"]} style={s.bar}>
      <View style={s.inner}>
        <Mark />
        <Text style={s.brand}>Cadence</Text>
        <Pressable onPress={() => events.length > 0 && setOpen(true)} accessibilityRole="button" accessibilityLabel="Choose event" disabled={events.length === 0} style={s.pick}>
          <Text numberOfLines={1} style={s.pickText}>{selected?.name ?? "No events yet"}</Text>
          <ChevronDown size={16} color={colors.muted} />
        </Pressable>
      </View>
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={s.scrim} onPress={() => setOpen(false)} accessibilityLabel="Close event list">
          <View style={s.sheet} accessibilityViewIsModal>
            <Text style={[type.title, { marginBottom: space.sm }]}>Event</Text>
            {events.map((e) => (
              <Pressable key={e.id} onPress={() => { select(e.id); setOpen(false); }} accessibilityRole="button" style={s.opt}>
                <Text style={[type.body, { flex: 1, fontFamily: e.id === selected?.id ? fonts.bold : fonts.body }]}>{e.name}</Text>
                {e.id === selected?.id ? <Check size={18} color={colors.brand} /> : null}
              </Pressable>
            ))}
          </View>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  bar: { backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.line },
  inner: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: space.lg, paddingVertical: 10 },
  brand: { fontFamily: fonts.display, fontSize: 19, color: colors.ink, letterSpacing: -0.4 },
  pick: { flex: 1, minHeight: 40, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, marginLeft: 6, paddingHorizontal: 14, borderRadius: radius.pill, backgroundColor: colors.canvas },
  pickText: { flex: 1, fontFamily: fonts.semi, fontSize: 13, color: colors.ink },
  scrim: { flex: 1, backgroundColor: "rgba(11,51,38,0.55)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: space.xl, paddingBottom: 36, gap: 2 },
  opt: { minHeight: 48, flexDirection: "row", alignItems: "center", gap: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.line },
});
