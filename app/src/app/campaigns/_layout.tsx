import { Stack } from "expo-router";

// Campaign screens stack inside the Campaigns tab; the event bar above them stays put.
export default function CampaignsLayout() {
  return <Stack screenOptions={{ headerShown: false, animation: "slide_from_right" }} />;
}
