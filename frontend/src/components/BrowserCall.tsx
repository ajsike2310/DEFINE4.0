import { useEffect, useRef, useState } from "react";
import { Mic, PhoneOff, Square, Volume2 } from "lucide-react";
import { api, ApiError } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import type { BrowserCall, BrowserReply } from "../types";
import { Badge, Button, inputCls } from "./ui";
import { OUTCOME_LABEL, OUTCOME_TONE } from "../services/labels";

/** Browser demo call. A person plays the participant: hear the script, then reply by key, text or voice.
 *  Replies go through the same rules as any call. It is recorded as SIMULATED and is never a phone call. */
export function BrowserCallDialog({ campaignId, recipientId, name, mode = "main", onClose }:
  { campaignId: number; recipientId: number; name: string; mode?: "main" | "clarify"; onClose: (changed: boolean) => void }) {
  const voice = useAsync(() => api.voiceStatus(), []);
  const [call, setCall] = useState<BrowserCall | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [reply, setReply] = useState<BrowserReply | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [recording, setRecording] = useState(false);
  const [playing, setPlaying] = useState(false);
  const rec = useRef<MediaRecorder | null>(null);
  const audioEl = useRef<HTMLAudioElement | null>(null);
  const callRef = useRef<BrowserCall | null>(null);
  const doneRef = useRef(false);
  const started = useRef(false);
  const closedRef = useRef(false);   // set on hang-up so a late recording or reply cannot act on a closed call

  useEffect(() => {
    if (started.current) return;                    // React StrictMode runs effects twice in dev
    started.current = true;
    api.startBrowserCall(campaignId, recipientId, mode)
      .then((c) => { callRef.current = c; setCall(c); })
      .catch((e: Error) => setStartError(e.message));
  }, [campaignId, recipientId, mode]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  function stopAudio() { audioEl.current?.pause(); audioEl.current = null; setPlaying(false); }

  async function close() {
    if (closedRef.current) return;
    closedRef.current = true;
    stopAudio();
    if (rec.current?.state === "recording") rec.current.stop();
    rec.current?.stream.getTracks().forEach((t) => t.stop());
    // An open call with no reply is ended without a guess, so it cannot block the participant.
    if (callRef.current && !doneRef.current) { try { await api.browserCallHangup(callRef.current.attempt_id); } catch { /* already closed */ } doneRef.current = true; }
    onClose(doneRef.current);
  }

  async function run(fn: () => Promise<BrowserReply>) {
    setBusy(true); setErr(null);
    try { const r = await fn(); doneRef.current = true; if (!closedRef.current) setReply(r); }
    catch (e) { if (!closedRef.current) setErr(e instanceof ApiError ? e.message : (e as Error).message); }
    finally { if (!closedRef.current) setBusy(false); }
  }

  async function play() {
    if (!call) return;
    setErr(null); setBusy(true);
    try {
      const blob = await api.browserCallSpeech(call.attempt_id);
      const url = URL.createObjectURL(blob);
      const a = new Audio(url);
      audioEl.current = a;
      a.onended = () => { setPlaying(false); URL.revokeObjectURL(url); };
      setPlaying(true);
      await a.play();
    } catch (e) { setPlaying(false); setErr((e as Error).message); }
    finally { setBusy(false); }
  }

  async function toggleRecord() {
    if (recording) { rec.current?.stop(); return; }
    setErr(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const mr = new MediaRecorder(stream);
      rec.current = mr;
      mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        if (call && chunks.length && !closedRef.current) void run(() => api.browserCallRespondAudio(call.attempt_id, new Blob(chunks, { type: mr.mimeType || "audio/webm" })));
      };
      mr.start();
      setRecording(true);
    } catch { setErr("The microphone is not available. Allow microphone access in the browser, or reply with a key or text."); }
  }

  const voiceOn = voice.data?.configured === true;
  const finished = reply !== null;

  return (
    <div className="fade-in fixed inset-0 z-[60] grid place-items-center bg-ink/45 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) void close(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="bc-title" className="dialog-in max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-lg border border-line bg-surface p-6 shadow-[0_20px_60px_rgba(15,35,32,.28)]">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="bc-title" className="text-base font-semibold text-ink">{mode === "clarify" ? "Clarification call" : "Call"}: {name}</h2>
          <Badge tone="warn">Browser demo, not a phone call</Badge>
        </div>
        <p className="mt-1 text-xs text-muted">You play the participant. What you reply is recorded as a simulated call.</p>

        {startError && <div role="alert" className="mt-4 rounded-md border border-bad/30 bg-bad/8 px-3 py-2 text-[13px] text-bad">{startError}</div>}
        {!call && !startError && <p role="status" className="mt-4 text-sm text-muted">Starting call…</p>}

        {call && (<>
          <div className="mt-4 rounded-lg border border-line bg-canvas p-3.5">
            <div className="mb-1 text-xs font-semibold text-muted">The call says ({call.language === "ml" ? "Malayalam" : "English"})</div>
            <p lang={call.language} className="text-[14px] leading-relaxed text-ink">{call.message}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button variant="secondary" onClick={play} disabled={busy || playing || !voiceOn}><Volume2 className="h-4 w-4" aria-hidden />{playing ? "Playing…" : "Play with ElevenLabs voice"}</Button>
              {!voiceOn && !voice.loading && <span className="text-xs text-muted">Voice is off: add ELEVENLABS_API_KEY to .env and restart the backend.</span>}
            </div>
          </div>

          {!finished && (<>
            <div className="mt-5">
              <div className="mb-2 text-xs font-semibold text-muted">Say it</div>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant={recording ? "danger" : "secondary"} onClick={toggleRecord} disabled={busy || !voiceOn} aria-pressed={recording}>
                  {recording ? <><Square className="h-4 w-4" aria-hidden />Stop and send</> : <><Mic className="h-4 w-4" aria-hidden />Speak your reply</>}</Button>
                <span className="text-xs text-muted">{voiceOn ? "Your voice is sent to ElevenLabs for transcription." : "Needs the ElevenLabs key."}</span>
              </div>
              {call.language === "ml" && <p className="mt-2 text-xs text-warn">Spoken Malayalam is transcribed unreliably in our tests (the text comes back in Roman letters and often wrong). A wrong transcript is sent to a person, never treated as a yes. Typing is the dependable way to answer.</p>}
              <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) void run(() => api.browserCallRespond(call.attempt_id, { text })); }}>
                <input className={inputCls} value={text} onChange={(e) => setText(e.target.value)} placeholder="Or type a reply, for example: Yes, I will be there" aria-label="Typed reply" maxLength={500} />
                <Button variant="secondary" disabled={busy || !text.trim()}>Send</Button>
              </form>
            </div>
          </>)}

          {err && <div role="alert" className="drop-in mt-4 rounded-md border border-bad/30 bg-bad/8 px-3 py-2 text-[13px] text-bad">{err}</div>}

          {reply && (
            <div role="status" className="panel-in mt-5 rounded-lg border border-line bg-surface p-4 text-[13.5px]">
              {reply.heard && <p className="text-ink-2">Heard: <q>{reply.heard}</q></p>}
              <p className="mt-1">Understood as <strong className="font-medium">{reply.intent?.replace(/_/g, " ") ?? "no reply"}</strong>
                {reply.method && <span className="text-xs text-muted"> (phrase rules{reply.evidence ? `: ${reply.evidence}` : ""})</span>}</p>
              <p className="mt-2 flex flex-wrap items-center gap-2">Participant outcome <Badge tone={OUTCOME_TONE[reply.outcome]}>{OUTCOME_LABEL[reply.outcome] ?? reply.outcome}</Badge>
                {reply.needs_review && <Badge tone="warn">Sent to a person to review</Badge>}</p>
              {reply.notes.length > 0 && <p className="mt-2 text-xs text-muted">{reply.notes.join("; ")}</p>}
            </div>)}
        </>)}

        <div className="mt-6 flex justify-end">
          <Button variant={finished ? "primary" : "secondary"} onClick={() => void close()}>{finished ? "Done" : <><PhoneOff className="h-4 w-4" aria-hidden />Hang up</>}</Button>
        </div>
      </div>
    </div>
  );
}
