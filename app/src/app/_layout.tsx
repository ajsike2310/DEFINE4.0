import { Tabs } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useFonts } from "expo-font";
import { HankenGrotesk_400Regular, HankenGrotesk_500Medium, HankenGrotesk_600SemiBold, HankenGrotesk_700Bold } from "@expo-google-fonts/hanken-grotesk";
import { NotoSansMalayalam_400Regular } from "@expo-google-fonts/noto-sans-malayalam";
import { Gauge, ListChecks, Megaphone, Menu, Users } from "lucide-react-native";
import { EventProvider } from "../hooks/useEvent";
import { EventBar } from "../components/EventBar";
import { colors, fonts } from "../theme";

export default function RootLayout() {
  const [loaded] = useFonts({ HankenGrotesk_400Regular, HankenGrotesk_500Medium, HankenGrotesk_600SemiBold, HankenGrotesk_700Bold, NotoSansMalayalam_400Regular });
  if (!loaded) return <View style={{ flex: 1, backgroundColor: colors.canvas }} />;
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <EventProvider>
        <Tabs
          screenOptions={{
            header: () => <EventBar />,
            tabBarActiveTintColor: colors.marigoldInk,
            tabBarInactiveTintColor: colors.muted,
            tabBarActiveBackgroundColor: colors.marigold,
            tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.line, height: 64, paddingTop: 6, paddingBottom: 8 },
            tabBarItemStyle: { borderRadius: 8, marginHorizontal: 4 },
            tabBarLabelStyle: { fontFamily: fonts.bold, fontSize: 11 },
          }}>
          <Tabs.Screen name="index" options={{ title: "Dashboard", tabBarIcon: ({ color }) => <Gauge size={20} color={color} /> }} />
          <Tabs.Screen name="campaigns" options={{ title: "Campaigns", tabBarIcon: ({ color }) => <Megaphone size={20} color={color} /> }} />
          <Tabs.Screen name="followups" options={{ title: "Queue", tabBarIcon: ({ color }) => <ListChecks size={20} color={color} /> }} />
          <Tabs.Screen name="participants" options={{ title: "People", tabBarIcon: ({ color }) => <Users size={20} color={color} /> }} />
          <Tabs.Screen name="settings" options={{ title: "More", tabBarIcon: ({ color }) => <Menu size={20} color={color} /> }} />
          <Tabs.Screen name="events" options={{ href: null }} />
          <Tabs.Screen name="analytics" options={{ href: null }} />
        </Tabs>
      </EventProvider>
    </SafeAreaProvider>
  );
}
