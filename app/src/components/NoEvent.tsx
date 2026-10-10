import { useRouter } from "expo-router";
import { useEvent } from "../hooks/useEvent";
import { Button, Card, Empty, ErrorState, Loading } from "./ui";

/** Shown by event-scoped screens until an event exists. Returns null once one is selected. */
export function NoEvent() {
  const { selected, loading, error, reload } = useEvent();
  const router = useRouter();
  if (loading && !selected) return <Loading />;
  if (error) return <ErrorState error={error} retry={() => void reload()} />;
  if (selected) return null;
  return (
    <Card>
      <Empty title="No event yet" body="Cadence works per event. Create one, then add a campaign."
        action={<Button title="Create an event" onPress={() => router.push("/events")} />} />
    </Card>
  );
}
