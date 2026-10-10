import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { api, ApiError } from "../services/api";
import { Button } from "./ui";

interface Result { imported: number; rejected: number; errors: { line: number; error: string }[] }

/** Add many participants at once from a CSV file. Without the consent confirmation they are stored with unknown
 *  consent and skipped at launch, exactly like people added one by one. */
export function ImportRecipients({ campaignId, onDone }: { campaignId: number; onDone: (r: Result) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function upload() {
    if (!file || busy) return;
    setBusy(true); setErr(null); setResult(null);
    try {
      const r = await api.importRecipients(campaignId, file, consent);
      setResult(r); onDone(r);
      if (r.imported > 0) { setFile(null); if (input.current) input.current.value = ""; }
    } catch (e) {
      setErr(e instanceof ApiError && e.details ? e.details.map((d) => d.message).join(" · ") : (e as Error).message);
    } finally { setBusy(false); }
  }

  return (
    <div className="border-b border-line-soft bg-canvas/60 p-5">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1 basis-72">
          <label htmlFor="csv-file" className="mb-1.5 block text-[12.5px] font-medium text-ink-2">CSV file</label>
          <input id="csv-file" ref={input} type="file" accept=".csv,text/csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); setErr(null); }}
            className="block w-full text-[13px] text-ink-2 file:mr-3 file:rounded-md file:border file:border-ink/80 file:bg-surface file:px-3 file:py-1.5 file:text-[13px] file:font-medium file:text-ink hover:file:bg-canvas" />
          <p className="mt-1.5 text-xs leading-snug text-muted">Columns: <b className="font-medium text-ink-2">name</b>, <b className="font-medium text-ink-2">phone</b> (with country code, e.g. +919876543210).
            Optional: participant_id, language, segment, opted_out (yes = never call).</p>
        </div>
        <Button onClick={() => void upload()} disabled={!file || busy}><Upload className="h-4 w-4" aria-hidden />{busy ? "Importing…" : "Import"}</Button>
      </div>
      <label className="mt-4 flex items-start gap-2.5 text-[13px] leading-relaxed text-ink-2">
        <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>I confirm these contacts are an authorised list and have agreed to receive calls of this kind. If left unticked, they are added with unknown consent and skipped at launch.</span>
      </label>
      {err && <p role="alert" className="drop-in mt-3 text-[13px] font-medium text-bad">{err}</p>}
      {result && (
        <div role="status" className="drop-in mt-3 text-[13px]">
          <p className="font-medium text-ink">{result.imported} imported{result.rejected ? `, ${result.rejected} rejected` : ""}.</p>
          {result.errors.length > 0 && (
            <ul className="mt-1.5 list-inside list-disc text-xs text-ink-2">
              {result.errors.slice(0, 5).map((x) => <li key={x.line}>Line {x.line}: {x.error}</li>)}
              {result.errors.length > 5 && <li>and {result.errors.length - 5} more</li>}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
