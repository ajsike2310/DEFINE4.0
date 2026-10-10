import { useState } from "react";
import { Link } from "react-router-dom";
import { Eye, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useEvent } from "../hooks/useEvent";
import { useNotify } from "../hooks/useNotify";
import { Badge, Button, Card, Empty, ErrorState, Loading, PageHeader, Segmented, Stat, StatGrid, Table } from "../components/ui";
import { NoEvent } from "../components/NoEvent";
import { EditCampaignDialog } from "../components/EditCampaign";
import { CAMPAIGN_TONE, PURPOSE_LABEL, fmtDate, pct } from "../services/labels";

export { CAMPAIGN_TONE };
const FILTERS: [string, string][] = [["", "All"], ["draft", "Draft"], ["running", "Running"], ["completed", "Completed"], ["cancelled", "Cancelled"]];

export default function Campaigns() {
  const { selected, reload: reloadEvents } = useEvent();
  const { success, error: fail, confirm } = useNotify();
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const { data, error, loading, reload } = useAsync(() => (selected ? api.campaignOverview(selected.id) : Promise.resolve(null)), [selected?.id]);
  const rows = (data?.campaigns ?? []).filter((c) => !status || c.status === status);

  async function remove(id: number, name: string) {
    if (busy) return;
    const yes = await confirm({ title: `Delete "${name}"?`, message: "This permanently removes the campaign with its participants, call history and follow-ups. It cannot be undone.", confirmLabel: "Delete campaign", cancelLabel: "Keep it", danger: true });
    if (!yes) return;
    setBusy(id);
    try { await api.deleteCampaign(id); success("Campaign deleted", name); reload(); void reloadEvents(); }
    catch (e) { fail("Could not delete the campaign", (e as Error).message); } finally { setBusy(null); }
  }

  return (
    <>
      <PageHeader title="Campaigns" subtitle={selected ? `Manage every campaign for ${selected.name}: progress, what needs you, and the next step.` : undefined}
        actions={selected && <Link to="/campaigns/new"><Button><Plus className="h-4 w-4" /> New campaign</Button></Link>} />
      <NoEvent />
      {selected && loading && !data && <Loading />}
      {error && <ErrorState error={error} retry={reload} />}
      {selected && data && (<>
        {data.campaigns.length > 0 && (
          <div className="mb-6">
            <StatGrid cols={4}>
              <Stat label="Campaigns" value={data.campaigns.length} hint={Object.entries(data.by_status).map(([k, n]) => `${n} ${k}`).join(", ")} />
              <Stat label="Participants" value={data.totals.participants} hint="Across all campaigns, per row" />
              <Stat label="Need follow-up" value={data.totals.needs_attention} accent={data.totals.needs_attention > 0} hint="Unresolved or not reached" />
              <Stat label="Retries ready" value={data.totals.retry_eligible} hint="Technical failures with attempts left" />
            </StatGrid>
          </div>)}
        <div className="mb-4"><Segmented label="Campaign status" value={status} onChange={setStatus} options={FILTERS} /></div>
        <Card flush>
          {rows.length === 0 ? <Empty title={data.campaigns.length ? "No campaigns match" : "No campaigns yet"} body={data.campaigns.length ? "Try a different status filter." : "Create your first campaign for this event."}
            action={!data.campaigns.length && <Link to="/campaigns/new"><Button><Plus className="h-4 w-4" /> New campaign</Button></Link>} /> : (
            <Table head={["Campaign", "Status", "Progress", "Next step", "Created", ""]}>
              {rows.map((c) => (
                <tr key={c.campaign_id}>
                  <td><Link className="font-medium text-ink underline decoration-ink/30 hover:decoration-ink" to={`/campaigns/${c.campaign_id}`}>{c.name}</Link> {c.is_demo && <Badge tone="warn">Simulated</Badge>}
                    <div className="text-xs text-muted">{PURPOSE_LABEL[c.purpose] ?? c.purpose}</div></td>
                  <td><Badge tone={CAMPAIGN_TONE[c.status]}>{c.status}</Badge></td>
                  <td className="min-w-40">
                    <div className="flex items-center gap-2" title={c.progress == null ? "No participants yet" : `${c.resolved} of ${c.participants} participants have a result`}>
                      <span className="h-1.5 w-24 overflow-hidden rounded-[2px] bg-line-soft"><span className="block h-full bg-brand transition-[width] duration-700" style={{ width: `${(c.progress ?? 0) * 100}%` }} /></span>
                      <span className="text-xs tabular-nums text-ink-2">{pct(c.progress)}</span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">{c.participants} participant{c.participants === 1 ? "" : "s"} · {c.contacted} contacted</div>
                  </td>
                  <td className={c.needs_attention || c.retry_eligible ? "font-medium text-signal" : "text-ink-2"}>{c.next_step}</td>
                  <td className="text-muted">{fmtDate(c.created_at)}</td>
                  <td className="whitespace-nowrap text-right">
                    <Link to={`/campaigns/${c.campaign_id}`} aria-label={`View ${c.name}`}><Button variant="ghost" tabIndex={-1} title="View"><Eye className="h-3.5 w-3.5" /><span className="hidden 2xl:inline"> View</span></Button></Link>
                    {(c.status === "draft" || c.status === "scheduled") && <Button variant="ghost" title="Edit" onClick={() => setEditing(c.campaign_id)} aria-label={`Edit ${c.name}`}><Pencil className="h-3.5 w-3.5" /><span className="hidden 2xl:inline"> Edit</span></Button>}
                    {c.status !== "running" && <Button variant="ghost" title="Delete" className="text-bad hover:bg-bad/10" disabled={busy === c.campaign_id} onClick={() => void remove(c.campaign_id, c.name)} aria-label={`Delete ${c.name}`}><Trash2 className="h-3.5 w-3.5" /><span className="hidden 2xl:inline"> Delete</span></Button>}
                  </td>
                </tr>
              ))}
            </Table>)}
        </Card>
      </>)}
      {editing !== null && <EditCampaignDialog campaignId={editing} onClose={(saved) => { setEditing(null); if (saved) { success("Campaign updated"); reload(); } }} />}
    </>
  );
}
