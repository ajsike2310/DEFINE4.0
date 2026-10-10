import { useEffect, useRef, useState } from "react";
import { Mic, PhoneOff, Play } from "lucide-react";
import { api, ApiError } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import type { BrowserCall, BrowserReply } from "../types";
import { Badge, Button } from "./ui";
import { OUTCOME_LABEL, OUTCOME_TONE } from "../services/labels";

type Phase = "idle" | "connecting" | "agent" | "listening" | "thinking" | "silent" | "ended" | "error";
type Turn = { who: "agent" | "you"; text: string };

const PHASE_LABEL: Record<Phase, string> = {
  idle: "Ready", connecting: "Connecting", agent: "Agent is speaking", listening: "Listening to you",
  thinking: "Working out your answer", silent: "No reply heard", ended: "Call ended", error: "Call stopped",
};

// Voice activity detection: speech starts above SPEECH_LEVEL and ends after QUIET_MS of quiet.
const SPEECH_LEVEL = 0.035, QUIET_MS = 1200, NO_SPEECH_MS = 9000, MAX_MS = 20000;

/** Hands-free simulated call. The agent speaks, listens for your reply, answers and ends the call, all by voice.
 *  The agent's words are fixed lines from the system (never generated), and what you say goes through the same
 *  rules as any reply. It is a browser demo, recorded as simulated, never a phone call. */
export function LiveCallDialog({ campaignId, recipientId, name, mode = "main", onClose }:
  { campaignId: number; recipientId: number; name: string; mode?: "main" | "clarify"; onClose: (changed: boolean) => void }) {
  const voice = useAsync(() => api.voiceStatus(), []);
  const [phase, setPhase] = useState<Phase>("idle");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [reply, setReply] = useState<BrowserReply | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [level, setLevel] = useState(0);
  const callRef = useRef<BrowserCall | null>(null);
  const doneRef = useRef(false);          // current attempt has a recorded reply
  const changedRef = useRef(false);       // anything was recorded at all
  const cancelled = useRef(false);
  const audioEl = useRef<HTMLAudioElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const logEnd = useRef<HTMLDivElement>(null);

  useEffect(() => { logEnd.current?.scrollIntoView?.({ block: "nearest" }); }, [turns, phase]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") void hangUp(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
  useEffect(() => () => { cancelled.current = true; audioEl.current?.pause(); streamRef.current?.getTracks().forEach((t) => t.stop()); }, []);

  const say = (who: Turn["who"], text: string) => setTurns((t) => [...t, { who, text }]);

  function play(blob: Blob): Promise<void> {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(blob);
      const a = new Audio(url);
      audioEl.current = a;
      a.onended = () => { URL.revokeObjectURL(url); resolve(); };
      a.onerror = () => { URL.revokeObjectURL(url); reject(new Error("The audio could not be played.")); };
      a.play().catch(reject);
    });
  }

  /** Records until the person has spoken and then gone quiet. Resolves null when nothing was said. */
  function listen(stream: MediaStream): Promise<Blob | null> {
    return new Promise((resolve) => {
      const ctx = new AudioContext();
      const an = ctx.createAnalyser();
      an.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(an);
      const mr = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      const buf = new Uint8Array(an.fftSize);
      const t0 = performance.now();
      let spoke = false, lastVoice = t0, over = false;
      const finish = (hasSpeech: boolean) => {
        if (over) return;
        over = true;
        clearInterval(timer);
        setLevel(0);
        const done = () => { void ctx.close(); resolve(hasSpeech && chunks.length ? new Blob(chunks, { type: mr.mimeType || "audio/webm" }) : null); };
        if (mr.state !== "inactive") { mr.onstop = done; mr.stop(); } else done();
      };
      const timer = setInterval(() => {
        if (over) return;
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) { const x = (v - 128) / 128; sum += x * x; }
        const rms = Math.sqrt(sum / buf.length);
        setLevel(Math.min(1, rms * 6));
        const now = performance.now();
        if (rms > SPEECH_LEVEL) { spoke = true; lastVoice = now; }
        if (cancelled.current) finish(false);
        else if (spoke && now - lastVoice > QUIET_MS) finish(true);
        else if (!spoke && now - t0 > NO_SPEECH_MS) finish(false);
        else if (now - t0 > MAX_MS) finish(spoke);
      }, 60);
      mr.start();
    });
  }

  async function converse(opening: BrowserCall) {
    let cur = opening;
    try {
      const stream = streamRef.current ?? await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      streamRef.current = stream;
      for (;;) {
        setPhase("agent"); say("agent", cur.message);
        await play(await api.browserCallSpeech(cur.attempt_id));
        if (cancelled.current) return;
        setPhase("listening");
        const heard = await listen(stream);
        if (cancelled.current) return;
        if (!heard) { setPhase("silent"); return; }
        setPhase("thinking");
        const r = await api.browserCallRespondAudio(cur.attempt_id, heard);
        doneRef.current = true; changedRef.current = true;
        setReply(r);
        say("you", r.heard ? `“${r.heard}”` : "(nothing clear)");
        if (r.next === "clarify") {                 // one spoken yes/no question, allowed once by the rules
          cur = await api.startBrowserCall(campaignId, recipientId, "clarify");
          callRef.current = cur; doneRef.current = false;
          continue;
        }
        setPhase("agent");
        const closing = await api.browserCallSpeakReply(cur.attempt_id);
        say("agent", closing.text);
        await play(closing.blob);
        setPhase("ended");
        return;
      }
    } catch (e) {
      if (cancelled.current) return;
      const msg = e instanceof ApiError ? e.message : e instanceof DOMException && e.name === "NotAllowedError"
        ? "The microphone is blocked. Allow it in the browser address bar and start again." : (e as Error).message;
      setErr(msg); setPhase("error");
    }
  }

  async function start() {
    setErr(null); setTurns([]); setReply(null); cancelled.current = false; setPhase("connecting");
    try {
      const c = await api.startBrowserCall(campaignId, recipientId, mode);
      callRef.current = c; doneRef.current = false;
      void converse(c);
    } catch (e) { setErr((e as Error).message); setPhase("error"); }
  }

  async function listenAgain() {            // after silence: same open call, listen once more
    if (!callRef.current) return;
    setErr(null); setPhase("listening"); cancelled.current = false;
    try {
      const stream = streamRef.current ?? await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      streamRef.current = stream;
      const heard = await listen(stream);
      if (!heard) { setPhase("silent"); return; }
      setPhase("thinking");
      const cur = callRef.current;
      const r = await api.browserCallRespondAudio(cur.attempt_id, heard);
      doneRef.current = true; changedRef.current = true; setReply(r);
      say("you", r.heard ? `“${r.heard}”` : "(nothing clear)");
      setPhase("agent");
      if (r.next === "clarify") { const q = await api.startBrowserCall(campaignId, recipientId, "clarify"); callRef.current = q; doneRef.current = false; void converse(q); return; }
      const closing = await api.browserCallSpeakReply(cur.attempt_id);
      say("agent", closing.text); await play(closing.blob); setPhase("ended");
    } catch (e) { setErr((e as Error).message); setPhase("error"); }
  }

  async function hangUp() {
    cancelled.current = true;
    audioEl.current?.pause();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    // An open call with no reply is ended without a guess, so it cannot block the participant.
    if (callRef.current && !doneRef.current) { try { await api.browserCallHangup(callRef.current.attempt_id); } catch { /* already closed */ } }
    onClose(changedRef.current);
  }

  const voiceOn = voice.data?.configured === true;
  const live = phase === "agent" || phase === "listening" || phase === "thinking" || phase === "connecting";
  const orb = phase === "listening" ? 1 + level * 0.9 : 1;

  return (
    <div className="fade-in fixed inset-0 z-[60] grid place-items-center bg-ink/45 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) void hangUp(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="lc-title" className="dialog-in max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-lg border border-line bg-surface p-6 shadow-[0_20px_60px_rgba(15,35,32,.28)]">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="lc-title" className="text-base font-semibold text-ink">Live call: {name}</h2>
          <Badge tone="warn">Browser demo, not a phone call</Badge>
        </div>
        <p className="mt-1 text-xs text-muted">You play the participant. Talk naturally: the agent speaks, waits for you, and answers. It is recorded as a simulated call.</p>

        <div className="mt-5 flex flex-col items-center">
          <div aria-hidden className="grid h-28 w-28 place-items-center">
            <div className={`h-20 w-20 rounded-full transition-transform duration-100 ${phase === "listening" ? "bg-brand/80" : phase === "agent" ? "bg-brand motion-safe:animate-pulse" : phase === "thinking" ? "bg-brand/40 motion-safe:animate-pulse" : "bg-line"}`}
              style={{ transform: `scale(${orb})` }} />
          </div>
          <p role="status" aria-live="polite" className="mt-1 text-sm font-medium text-ink">{PHASE_LABEL[phase]}</p>
        </div>

        {turns.length > 0 && (
          <ol aria-label="Call transcript" className="mt-4 max-h-56 space-y-2 overflow-y-auto rounded-lg border border-line bg-canvas p-3 text-[13.5px]">
            {turns.map((t, i) => (
              <li key={i} className={t.who === "you" ? "text-right" : ""}>
                <span className="block text-[11px] text-muted">{t.who === "you" ? "You" : "Agent"}</span>
                <span className={`inline-block max-w-[92%] rounded-lg px-2.5 py-1.5 text-left ${t.who === "you" ? "bg-brand-soft text-ink" : "bg-surface text-ink-2 border border-line"}`}>{t.text}</span>
              </li>))}
            <div ref={logEnd} />
          </ol>)}

        {!voiceOn && !voice.loading && <div role="alert" className="mt-4 rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-[13px] text-warn">Voice is off. Add ELEVENLABS_API_KEY to .env and restart the backend, or use a manual call.</div>}
        {err && <div role="alert" className="drop-in mt-4 rounded-md border border-bad/30 bg-bad/8 px-3 py-2 text-[13px] text-bad">{err}</div>}
        {phase === "silent" && <p className="mt-4 text-[13px] text-ink-2">Nothing was heard, so nothing was recorded. Try again, or hang up and the participant stays as they were.</p>}

        {reply && (phase === "ended" || phase === "silent") && (
          <div className="panel-in mt-4 rounded-lg border border-line bg-surface p-4 text-[13.5px]">
            <p>Understood as <strong className="font-medium">{reply.intent?.replace(/_/g, " ") ?? "no reply"}</strong>
              {reply.method && <span className="text-xs text-muted"> (phrase rules{reply.evidence ? `: ${reply.evidence}` : ""})</span>}</p>
            <p className="mt-2 flex flex-wrap items-center gap-2">Participant outcome <Badge tone={OUTCOME_TONE[reply.outcome]}>{OUTCOME_LABEL[reply.outcome] ?? reply.outcome}</Badge>
              {reply.needs_review && <Badge tone="warn">Sent to a person to review</Badge>}</p>
            {reply.notes.length > 0 && <p className="mt-2 text-xs text-muted">{reply.notes.join("; ")}</p>}
          </div>)}

        <div className="mt-6 flex flex-wrap justify-end gap-2">
          {(phase === "idle" || phase === "error") && <Button onClick={() => void start()} disabled={!voiceOn}><Play className="h-4 w-4" aria-hidden />{phase === "error" ? "Start again" : "Start live call"}</Button>}
          {phase === "silent" && <Button onClick={() => void listenAgain()}><Mic className="h-4 w-4" aria-hidden />Listen again</Button>}
          <Button variant={phase === "ended" ? "primary" : "secondary"} onClick={() => void hangUp()}>
            {phase === "ended" ? "Done" : <><PhoneOff className="h-4 w-4" aria-hidden />{live ? "Hang up" : "Close"}</>}</Button>
        </div>
      </div>
    </div>
  );
}
