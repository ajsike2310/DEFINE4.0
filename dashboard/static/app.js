"use strict";
/* Outreach dashboard: hash-routed single page, no build step. All user data is escaped through esc(). */

const $ = (s, r = document) => r.querySelector(s);
const app = $("#app");
let META = null, pollTimer = null;

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const OUTCOME_ORDER = ["confirmed", "declined", "callback_requested", "information_requested", "acknowledged", "opted_out",
  "unclear", "needs_review", "no_response", "voicemail", "no_answer", "busy", "failed", "in_progress", "pending"];
const UNREACHED = ["no_answer", "busy", "failed", "voicemail"];
const NON_RESPONDER = [...UNREACHED, "no_response", "unclear", "needs_review"];

// ---------------------------------------------------------------- api / ui helpers
async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  const tok = sessionStorage.getItem("token");
  if (tok) headers["Authorization"] = "Bearer " + tok;
  const res = await fetch("/api" + path, { method: opts.method || "GET", headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (res.status === 401) {
    const t = prompt("Enter the dashboard access token");
    if (t) { sessionStorage.setItem("token", t.trim()); return api(path, opts); }
    throw new Error("Access token required");
  }
  if (res.status === 204) return null;
  const isText = (res.headers.get("content-type") || "").startsWith("text/");
  const data = isText ? await res.text() : await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg.replace(/^Value error, /, "")).join("; ") : "Something went wrong");
  }
  return data;
}
function toast(msg, err = false) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : ""); t.textContent = msg;
  $("#toasts").append(t); setTimeout(() => t.remove(), err ? 6000 : 3200);
}
const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { toast(e.message, true); } };
const fmtDate = (d, t) => {
  if (!d) return "Date not set";
  const [y, m, dd] = d.split("-").map(Number);
  const s = new Date(y, m - 1, dd).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  if (!t) return s;
  const [h, mi] = t.split(":").map(Number);
  return s + ", " + new Date(2000, 0, 1, h, mi).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
};
const pct = (n, t) => (t ? Math.round((100 * n) / t) : 0);
const label = (o) => META.outcomes[o] || o;
const dot = (o) => `<span class="dot" style="background:var(--c-${o})" aria-hidden="true"></span>`;
const pill = (o) => `<span class="nowrap" style="display:inline-flex;gap:6px;align-items:center">${dot(o)}${esc(label(o))}</span>`;
const stateBadge = (s) => `<span class="badge state-${s}">${{ draft: "Draft", ready: "Ready", running: "Calling…", waiting: "Retrying later", paused: "Paused", completed: "Completed" }[s] || s}</span>`;

function stack(counts, total) {
  const segs = OUTCOME_ORDER.filter((k) => counts[k]).map((k) => `<i style="width:${(100 * counts[k]) / total}%;background:var(--c-${k})" title="${esc(label(k))}: ${counts[k]}"></i>`);
  return `<div class="bar" role="img" aria-label="Outcome breakdown">${segs.join("")}</div>`;
}
function legend(rows) {
  const counts = {}; rows.forEach((s) => Object.entries(s.counts).forEach(([k, v]) => (counts[k] = (counts[k] || 0) + v)));
  return `<div class="legend">${OUTCOME_ORDER.filter((k) => counts[k]).map((k) => `<span>${dot(k)}${esc(label(k))} <b>${counts[k]}</b></span>`).join("")}</div>`;
}
function breakdown(items, linkFor) {
  if (!items.length) return `<p class="muted">No calls yet.</p>`;
  return items.map((it) => {
    const s = it.summary, name = linkFor ? `<a href="${linkFor(it)}">${esc(it.label)}</a>` : esc(it.label);
    return `<div class="row-bar"><div>${name}${it.sub ? `<div class="muted small">${esc(it.sub)}</div>` : ""}</div>
      ${s.total ? stack(s.counts, s.total) : `<div class="bar"></div>`}
      <div class="small muted nowrap" style="text-align:right"><b style="color:var(--text)">${s.confirmed}</b>/${s.total} confirmed</div></div>`;
  }).join("");
}

const RETRY_CHOICES = { off: "Don't retry automatically", 5: "Retry after 5 minutes", 15: "Retry after 15 minutes", 30: "Retry after 30 minutes",
  60: "Retry after 1 hour", 120: "Retry after 2 hours", 240: "Retry after 4 hours" };
const retryValue = (c) => (c.auto_retry ? String(c.retry_interval_min) : "off");
const retryBody = (v) => (v === "off" ? { auto_retry: false, retry_interval_min: 30 } : { auto_retry: true, retry_interval_min: +v });
const when = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }); };

// ---------------------------------------------------------------- modal
function modal(title, body, { wide = false, submit = "Save", onSubmit } = {}) {
  const root = $("#modal-root");
  root.innerHTML = `<div class="overlay"><form class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
    <h2>${esc(title)}</h2>${body}<div class="modal-actions"><button type="button" class="btn" data-close>Cancel</button>
    ${onSubmit ? `<button class="btn primary" type="submit">${esc(submit)}</button>` : ""}</div></form></div>`;
  const close = () => (root.innerHTML = "");
  root.querySelector("[data-close]").onclick = close;
  root.querySelector(".overlay").addEventListener("mousedown", (e) => { if (e.target.classList.contains("overlay")) close(); });
  const form = root.querySelector("form");
  form.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  form.onsubmit = async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button[type=submit]"); btn.disabled = true;
    try { await onSubmit(Object.fromEntries(new FormData(form)), form); close(); } catch (err) { toast(err.message, true); btn.disabled = false; }
  };
  const first = form.querySelector("input,select,textarea"); if (first) first.focus();
  return { form, close };
}
const field = (name, lbl, val = "", extra = "") => `<div><label for="f_${name}">${lbl}</label><input id="f_${name}" name="${name}" value="${esc(val)}" ${extra}></div>`;
const select = (name, lbl, opts, val) => `<div><label for="f_${name}">${lbl}</label><select id="f_${name}" name="${name}">${Object.entries(opts).map(([k, v]) => `<option value="${esc(k)}" ${k === val ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></div>`;

// ---------------------------------------------------------------- router
const routes = [
  [/^#\/?$/, "overview", overview],
  [/^#\/events$/, "events", events],
  [/^#\/events\/(\d+)$/, "events", eventPage],
  [/^#\/campaigns\/(\d+)$/, "events", campaignPage],
  [/^#\/followups$/, "followups", followups],
  [/^#\/settings$/, "settings", settings],
];
async function route() {
  clearTimeout(pollTimer);
  if (!META) META = await api("/meta").catch((e) => { app.innerHTML = `<div class="card empty"><h3>Cannot reach the server</h3><p>${esc(e.message)}</p></div>`; return null; });
  if (!META) return;
  const b = $("#mode-badge");
  b.className = "badge " + (META.simulated ? "sim" : "live");
  b.textContent = META.simulated ? "Simulated calls (demo)" : "Live calls · " + META.provider;
  const hash = location.hash || "#/";
  for (const [re, nav, fn] of routes) {
    const m = hash.match(re);
    if (m) {
      document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === nav));
      app.innerHTML = `<div class="loading">Loading…</div>`;
      refreshTaskCount();
      try { await fn(...m.slice(1).map(Number)); } catch (e) { app.innerHTML = `<div class="card empty"><h3>Something went wrong</h3><p>${esc(e.message)}</p><a class="btn" href="#/">Back to overview</a></div>`; }
      return;
    }
  }
  location.hash = "#/";
}
window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", route);

// ---------------------------------------------------------------- overview
async function overview() {
  const o = await api("/overview"), t = o.totals;
  const kpi = (v, l) => `<div class="card kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`;
  app.innerHTML = `
    <div class="page-head"><div><h1>Overview</h1><div class="muted">Outcomes across every campaign</div></div>
      <div class="actions"><a class="btn primary" href="#/events">＋ New event</a></div></div>
    <div class="grid g4">${kpi(o.events, "Events")}${kpi(t.total, "Calls planned")}${kpi(t.confirmed, "Confirmed attending")}
      ${kpi(t.reach_rate + "%", "Reached (picked up)")}${kpi(t.response_rate + "%", "Gave an answer")}
      <a href="#/followups" class="card kpi" style="color:inherit;text-decoration:none"><div class="v">${o.open_tasks}</div><div class="l">Open follow-up tasks →</div></a></div>
    <div class="card" style="margin-top:16px"><h2>RSVP across all events</h2><div class="legend"><span><b class="rsvp-attending">${o.rsvp.attending}</b> attending</span><span><b class="rsvp-not_attending">${o.rsvp.not_attending}</b> not attending</span><span><b class="rsvp-undecided">${o.rsvp.undecided}</b> undecided (needs a person)</span></div></div>
    ${t.total === 0 ? `<div class="card empty" style="margin-top:16px"><h3>No calls yet</h3><p>Create an event, add the people to invite, then start a campaign. Results will appear here.</p><a class="btn primary" href="#/events">Create your first event</a></div>` : `
    <div class="card"><h2>Outcomes by campaign</h2>${legend([t])}
      <div style="margin-top:8px">${breakdown(o.by_campaign.filter((c) => c.summary.total).map((c) => ({ ...c, label: c.name, sub: c.event_name })), (c) => "#/campaigns/" + c.id)}</div></div>
    <div class="grid g2" style="margin-top:16px">
      <div class="card"><h2>By language</h2>${breakdown(o.by_language)}</div>
      <div class="card"><h2>By audience segment</h2>${breakdown(o.by_segment)}</div></div>`}`;
}

// ---------------------------------------------------------------- events
async function events() {
  const list = await api("/events");
  app.innerHTML = `
    <div class="page-head"><div><h1>Events</h1><div class="muted">Webinars, hackathons, workshops, reminders and more</div></div>
      <div class="actions"><button class="btn primary" id="new-event">＋ New event</button></div></div>
    ${list.length ? `<div class="grid g3">${list.map((e) => `
      <a class="card event-card" href="#/events/${e.id}"><span class="chip">${esc(META.event_types[e.type]?.label || e.type)}</span>
        <h3>${esc(e.name)}</h3><div class="muted small">${esc(fmtDate(e.event_date, e.event_time))}${e.mode === "online" ? " · Online" : e.venue ? " · " + esc(e.venue) : ""}</div>
        <div class="stats"><div><b>${e.participants}</b>People</div><div><b>${e.campaigns}</b>Campaigns</div><div><b>${e.confirmed}</b>Attending</div>${e.open_tasks ? `<div><b style="color:var(--warn)">${e.open_tasks}</b>Follow-ups</div>` : ""}</div></a>`).join("")}</div>`
      : `<div class="card empty"><h3>No events yet</h3><p>An event holds your guest list and the call campaigns for it.</p><button class="btn primary" id="new-event2">Create an event</button></div>`}`;
  $("#new-event").onclick = () => eventForm();
  if ($("#new-event2")) $("#new-event2").onclick = () => eventForm();
}

function eventForm(ev) {
  const types = Object.fromEntries(Object.entries(META.event_types).map(([k, v]) => [k, v.label]));
  const e = ev || { type: "webinar", mode: "online" };
  const m = modal(ev ? "Edit event" : "New event", `<div class="form">
    ${field("name", "Event name", e.name, "required maxlength=120 placeholder=\"e.g. AI Hack Night 2026\"")}
    <div class="two">${select("type", "Type", types, e.type)}${select("mode", "Format", { online: "Online", in_person: "In person" }, e.mode)}</div>
    <div class="two">${field("event_date", "Date", e.event_date, "type=date")}${field("event_time", "Start time", e.event_time, "type=time")}</div>
    ${field("venue", "Venue (or leave empty for online)", e.venue, "placeholder=\"Main auditorium, Block A\"")}
    ${field("organiser", "Organiser (said at the start of the call)", e.organiser, "placeholder=\"Your institution\"")}
    <div><label for="f_description">About this event (optional)</label>
      <textarea id="f_description" name="description" style="min-height:70px" maxlength="400" placeholder="One or two sentences. If someone asks “what is this about?” on the call, the agent says exactly this.">${esc(e.description)}</textarea></div>
    <div class="hint">For a payment reminder, put the due date in “Date” and add an <code>amount</code> column to your list.</div></div>`,
    { submit: ev ? "Save changes" : "Create event", onSubmit: async (d) => {
      const saved = await api(ev ? "/events/" + ev.id : "/events", { method: ev ? "PATCH" : "POST", body: { ...d, event_date: d.event_date || null, event_time: d.event_time || null } });
      toast(ev ? "Event updated" : "Event created"); location.hash = "#/events/" + saved.id; if (ev) route();
    } });
  m.form.querySelector("[name=type]").onchange = (x) => { m.form.querySelector("[name=mode]").value = META.event_types[x.target.value].mode; };
}

// ---------------------------------------------------------------- event detail
async function eventPage(id) {
  const [ev, people, camps] = await Promise.all([api("/events/" + id), api(`/events/${id}/participants`), api(`/events/${id}/campaigns`)]);
  const tab = sessionStorage.getItem("tab-" + id) || (people.length && camps.length ? "campaigns" : people.length ? "campaigns" : "people");
  const draw = () => {
    const cur = sessionStorage.getItem("tab-" + id) || tab;
    app.innerHTML = `
      <div class="crumbs"><a href="#/events">Events</a> / ${esc(ev.name)}</div>
      <div class="page-head"><div><h1>${esc(ev.name)}</h1>
        <div class="muted">${esc(META.event_types[ev.type]?.label)} · ${esc(fmtDate(ev.event_date, ev.event_time))} · ${ev.mode === "online" ? "Online" : esc(ev.venue || "Venue not set")}${ev.organiser ? " · " + esc(ev.organiser) : ""}</div></div>
        <div class="actions"><button class="btn" id="edit-ev">Edit event</button><button class="btn danger" id="del-ev">Delete</button></div></div>
      <div class="tabs" role="tablist"><button data-tab="people" class="${cur === "people" ? "active" : ""}">People (${people.length})</button>
        <button data-tab="campaigns" class="${cur === "campaigns" ? "active" : ""}">Campaigns (${camps.length})</button></div>
      <div id="tab-body"></div>`;
    $("#edit-ev").onclick = () => eventForm(ev);
    $("#del-ev").onclick = guard(async () => { if (confirm(`Delete “${ev.name}”, its ${people.length} people and all call records? This cannot be undone.`)) { await api("/events/" + id, { method: "DELETE" }); toast("Event deleted"); location.hash = "#/events"; } });
    app.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { sessionStorage.setItem("tab-" + id, b.dataset.tab); draw(); }));
    cur === "people" ? peopleTab(ev, people, $("#tab-body")) : campaignsTab(ev, people, camps, $("#tab-body"));
  };
  draw();
}

function peopleTab(ev, people, el) {
  el.innerHTML = `<div class="card">
    <div class="page-head" style="margin-bottom:8px"><h2 style="margin:0">Guest list</h2><div class="actions">
      <button class="btn" id="imp">Import CSV</button><button class="btn primary" id="add">＋ Add person</button></div></div>
    ${people.length ? `<div class="table-wrap"><table><thead><tr><th>Name</th><th>Phone</th><th>Language</th><th>Segment</th><th>RSVP</th><th>In campaigns</th><th></th></tr></thead><tbody>
      ${people.map((p) => `<tr><td>${esc(p.name)}${p.opted_out ? ` <span class="badge" title="Asked not to be called">Opted out</span>` : !p.can_call ? ` <span class="badge" title="Not OK to call">Do not call</span>` : ""}</td><td class="nowrap">${esc(p.phone)}</td>
        <td>${esc(META.languages[p.language] || "Campaign default")}</td><td>${esc(p.segment || "—")}</td>
        <td>${rsvpLabel(p.rsvp)}</td>
        <td class="small">${p.campaigns.length ? p.campaigns.map(esc).join(", ") : `<span class="muted">Not in any campaign</span>`}</td>
        <td class="nowrap" style="text-align:right"><button class="btn sm" data-edit="${p.id}">Edit</button> <button class="btn sm danger" data-del="${p.id}">Erase</button></td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty"><h3>Nobody on the list yet</h3><p>Add people one by one, or import a CSV with <code>name, phone</code> columns.<br>Optional columns: language, segment, plus any custom field. You choose who is called, and what each person hears, inside each campaign.</p></div>`}</div>`;
  $("#add", el).onclick = () => personForm(ev);
  $("#imp", el).onclick = () => importForm(ev);
  el.querySelectorAll("[data-edit]").forEach((b) => (b.onclick = () => personForm(ev, people.find((p) => p.id == b.dataset.edit))));
  el.querySelectorAll("[data-del]").forEach((b) => (b.onclick = guard(async () => {
    const p = people.find((x) => x.id == b.dataset.del);
    if (confirm(`Erase ${p.name} and all their call records? This cannot be undone.`)) { await api("/participants/" + p.id, { method: "DELETE" }); toast("Erased"); route(); }
  })));
}

function personForm(ev, p) {
  const x = p || { fields: {} };
  const extra = Object.entries(x.fields).map(([k, v]) => `${k}=${v}`).join("\n");
  modal(p ? "Edit person" : "Add person", `<div class="form">
    <div class="two">${field("name", "Name", x.name, "required")}${field("phone", "Mobile number", x.phone, "required placeholder=\"98765 43210\"")}</div>
    <div class="two">${select("language", "Call language", { "": "Use campaign default", ...META.languages }, x.language || "")}${field("segment", "Segment / group", x.segment, "placeholder=\"Students, Mentors, Speakers…\"")}</div>
    <label class="switch" style="font-weight:600"><input type="checkbox" name="can_call" ${x.can_call === false ? "" : "checked"}> OK to call this person</label>
    <div class="hint" style="margin-top:-8px">Untick if they have not agreed to receive calls. They stay on the list but are never dialled.</div>
    <div><label for="f_extra">Extra fields (optional, one per line as <code>key=value</code>)</label>
      <textarea id="f_extra" name="extra" style="min-height:64px" placeholder="amount=Rs 5000">${esc(extra)}</textarea></div></div>`,
    { onSubmit: async (d) => {
      const fields = {}; d.extra.split("\n").forEach((l) => { const i = l.indexOf("="); if (i > 0) fields[l.slice(0, i).trim()] = l.slice(i + 1).trim(); });
      const { extra: _x, ...body } = d;
      await api(p ? "/participants/" + p.id : `/events/${ev.id}/participants`, { method: p ? "PATCH" : "POST", body: { ...body, fields, can_call: d.can_call === "on" } });
      toast(p ? "Saved" : "Person added"); route();
    } });
}

function importForm(ev) {
  const m = modal("Import people from CSV", `<div class="form">
    <p class="muted small" style="margin:0">First row must be a header. Required: <b>name</b>, <b>phone</b>. Optional: <b>language</b> (en/hi/ta), <b>segment</b>. Any other column (for example <b>amount</b>) becomes a variable like <code>{amount}</code>.</p>
    <div><label for="f_file">CSV file</label><input id="f_file" type="file" accept=".csv,text/csv,.txt"></div>
    <div><label for="f_csv">…or paste rows</label><textarea id="f_csv" name="csv" style="min-height:140px;font-family:ui-monospace,Consolas,monospace;font-size:13px" placeholder="name,phone,language,segment&#10;Asha Rao,9876543210,en,Students"></textarea></div></div>`,
    { submit: "Import", onSubmit: async (d) => {
      if (!d.csv.trim()) throw new Error("Choose a file or paste some rows");
      const r = await api(`/events/${ev.id}/participants/import`, { method: "POST", body: { csv: d.csv } });
      toast(`${r.added} added` + (r.error_count ? `, ${r.error_count} skipped (${r.errors.slice(0, 2).map((e) => `row ${e.row}: ${e.error}`).join("; ")})` : ""), r.added === 0);
      route();
    } });
  $("#f_file").onchange = async (e) => { const f = e.target.files[0]; if (f) $("#f_csv").value = await f.text(); };
}

function campaignsTab(ev, people, camps, el) {
  el.innerHTML = `<div class="actions" style="justify-content:flex-end;margin-bottom:12px"><button class="btn primary" id="new-camp">＋ New campaign</button></div>
    ${camps.length ? `<div class="grid g3">${camps.map((c) => `<a class="card event-card" href="#/campaigns/${c.id}">
      <div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><span class="chip">${esc(META.purposes[c.purpose])}</span>${stateBadge(c.state)}</div>
      <h3>${esc(c.name)}</h3><div class="muted small">${esc(META.languages[c.language])} · ${c.summary.total} ${c.summary.total === 1 ? "person" : "people"}</div>
      <div style="margin:12px 0 8px">${c.summary.total ? stack(c.summary.counts, c.summary.total) : `<div class="bar"></div>`}</div>
      <div class="stats"><div><b>${c.summary.total}</b>Calls</div><div><b>${c.summary.confirmed}</b>Confirmed</div><div><b>${c.summary.reach_rate}%</b>Reached</div></div></a>`).join("")}</div>`
      : `<div class="card empty"><h3>No campaigns yet</h3><p>A campaign is one round of calls to this event's list: an invitation, a reminder, an update.</p></div>`}`;
  $("#new-camp", el).onclick = () => {
    modal("New campaign", `<div class="form">${field("name", "Campaign name", "", "required placeholder=\"e.g. First invitation\"")}
      <div class="two">${select("purpose", "Purpose", META.purposes, "invite")}${select("language", "Call language", META.languages, "en")}</div>
      <div class="two">${select("add_all", "Who is in it", { no: "Nobody yet (I'll pick people)", yes: `Everyone on the list (${people.filter((p) => !p.opted_out).length})` }, people.length ? "yes" : "no")}
        ${select("max_attempts", "Max attempts per person", { 1: "1", 2: "2", 3: "3", 4: "4", 5: "5" }, String(META.max_attempts))}</div>
      ${select("retry", "If someone doesn't pick up or doesn't answer", RETRY_CHOICES, "30")}
      <div class="hint">Each campaign has its own people and its own personal messages. The call script is prefilled; edit it, preview it and add or personalise people on the next screen.</div></div>`,
      { submit: "Create campaign", onSubmit: async (d) => {
        const c = await api(`/events/${ev.id}/campaigns`, { method: "POST", body: { ...d, ...retryBody(d.retry), add_all: d.add_all === "yes", max_attempts: +d.max_attempts, template: "" } });
        toast("Campaign created"); location.hash = "#/campaigns/" + c.id;
      } });
  };
}

// ---------------------------------------------------------------- campaign page
async function campaignPage(id) {
  const c = await api("/campaigns/" + id);
  const ev = await api("/events/" + c.event_id);
  let people = await api(`/events/${c.event_id}/participants`);
  let filter = "all", previewFn = () => {};
  app.innerHTML = `
    <div class="crumbs"><a href="#/events">Events</a> / <a href="#/events/${ev.id}">${esc(ev.name)}</a> / ${esc(c.name)}</div>
    <div id="camp-head"></div>
    <div class="card" id="editor"></div>
    <div class="card" id="results"></div>`;
  const state = { c };
  const isActive = (x) => ["pending", "in_progress"].includes(x.outcome);

  function head() {
    const cur = state.c, s = cur.summary, running = cur.state === "running";
    const toCall = cur.calls.filter((x) => x.status === "pending" && !x.opted_out).length;
    const retryable = cur.calls.filter((x) => NON_RESPONDER.includes(x.outcome) && !x.opted_out && x.attempts < cur.max_attempts).length;
    $("#camp-head").innerHTML = `
      <div class="page-head"><div><h1>${esc(cur.name)} ${stateBadge(cur.state)}</h1>
        <div class="muted">${esc(META.purposes[cur.purpose])} · ${esc(META.languages[cur.language])} · ${s.total} ${s.total === 1 ? "person" : "people"} · up to ${cur.max_attempts} attempts · ${cur.auto_retry ? `auto-retry after ${cur.retry_interval_min} min` : "no auto-retry"}</div>
        ${cur.next_retry_at ? `<div class="banner" style="margin-top:8px">Retrying ${s.retries_scheduled} ${s.retries_scheduled === 1 ? "person" : "people"} automatically, next at about ${esc(when(cur.next_retry_at))}.</div>` : ""}</div>
        <div class="actions">
          <button class="btn" id="add-people">＋ Add people</button>
          ${running ? `<button class="btn" id="pause">⏸ Pause</button>` : `<button class="btn primary" id="start" ${toCall ? "" : "disabled"}>${s.total - toCall > 0 ? "▶ Call remaining" : "▶ Start calls"}${toCall ? ` (${toCall})` : ""}</button>`}
          <button class="btn" id="retry" ${retryable ? "" : "disabled"} title="Call again everyone who did not pick up or did not give a clear answer">↻ Retry non-responders${retryable ? ` (${retryable})` : ""}</button>
          <a class="btn" href="/api/campaigns/${cur.id}/export.csv" id="export">⬇ Export CSV</a>
          <button class="btn" id="camp-settings">Settings</button>
          <button class="btn danger" id="del" ${running ? "disabled" : ""}>Delete</button></div></div>
      <div class="grid g4">
        <div class="card kpi"><div class="v">${s.total}</div><div class="l">People in campaign</div></div>
        <div class="card kpi"><div class="v">${s.confirmed}</div><div class="l">Confirmed attending</div></div>
        <div class="card kpi"><div class="v">${s.reach_rate}%</div><div class="l">Picked up</div></div>
        <div class="card kpi"><div class="v">${cur.calls.filter((x) => x.needs_review).length}</div><div class="l">Need human follow-up</div></div></div>
      ${s.total ? `<div class="card" style="margin-top:16px">${stack(s.counts, s.total)}<div style="margin-top:10px">${legend([s])}</div></div>` : ""}`;
    const act = (sel, fn) => { const b = $(sel); if (b) b.onclick = guard(fn); };
    act("#add-people", async () => addPeople());
    act("#camp-settings", async () => campaignSettings());
    act("#start", async () => {
      if (!confirm(META.simulated ? `Run a simulated campaign for ${toCall} people? No real calls are placed in demo mode.` : `Place real calls to ${toCall} people now? Each person hears their own message.`)) return;
      const r = await api(`/campaigns/${cur.id}/launch`, { method: "POST" }); toast(`Calling ${r.queued} people`); await refresh();
    });
    act("#pause", async () => { await api(`/campaigns/${cur.id}/pause`, { method: "POST" }); toast("Paused. Calls already ringing will finish."); await refresh(); });
    act("#retry", async () => {
      if (!confirm(`Call ${retryable} non-responders again?`)) return;
      await api(`/campaigns/${cur.id}/retry`, { method: "POST" }); toast("Retrying non-responders"); await refresh();
    });
    act("#del", async () => { if (confirm("Delete this campaign and its call records?")) { await api("/campaigns/" + cur.id, { method: "DELETE" }); location.hash = "#/events/" + ev.id; } });
    $("#export").onclick = guard(async (e) => {      // fetch (not a plain link) so the access token is sent
      e.preventDefault();
      const csv = await api(`/campaigns/${cur.id}/export.csv`);
      const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); a.download = `campaign-${cur.id}-results.csv`; a.click();
    });
  }

  // ---- campaign settings: name, attempts, automatic retries
  function campaignSettings() {
    const cur = state.c;
    modal("Campaign settings", `<div class="form">${field("name", "Campaign name", cur.name, "required")}
      <div class="two">${select("max_attempts", "Max attempts per person", { 1: "1", 2: "2", 3: "3", 4: "4", 5: "5" }, String(cur.max_attempts))}
        ${select("retry", "If someone doesn't pick up or doesn't answer", RETRY_CHOICES, retryValue(cur))}</div>
      <div class="hint">Automatic retries only run while the campaign is started and not paused, inside your calling hours, and never for people who opted out or are marked not OK to call. After the last attempt a follow-up task is created for a person to contact them.</div></div>`,
      { submit: "Save settings", onSubmit: async (d) => {
        await api("/campaigns/" + cur.id, { method: "PATCH", body: { name: d.name, purpose: cur.purpose, language: cur.language, template: cur.template, max_attempts: +d.max_attempts, ...retryBody(d.retry) } });
        toast("Settings saved"); await refresh();
      } });
  }

  // ---- add people: pick from the event list, create a new person, or import a CSV
  function addPeople() {
    const inCampaign = new Set(state.c.calls.map((x) => x.participant_id));
    const avail = people.filter((p) => !p.opted_out && p.can_call && !inCampaign.has(p.id));
    const segs = [...new Set(avail.map((p) => p.segment).filter(Boolean))];
    const varsHint = `Variables: ${META.variables.map((v) => "{" + v + "}").join(" ")}`;
    const m = modal("Add people to this campaign", `<div class="form">
      <input type="hidden" name="mode" value="pick">
      <div class="tabs" id="ap-tabs"><button type="button" data-m="pick" class="active">From event list (${avail.length})</button><button type="button" data-m="new">New person</button><button type="button" data-m="csv">Import CSV</button></div>
      <section data-s="pick">
        ${avail.length ? `<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><input id="ap-search" type="search" placeholder="Search name or number" style="flex:1;min-width:180px">
          <select id="ap-seg" style="width:auto"><option value="">All segments</option>${segs.map((s) => `<option>${esc(s)}</option>`).join("")}</select>
          <label style="margin:0;font-weight:500"><input type="checkbox" id="ap-all" style="width:auto"> Select all shown</label></div>
          <div id="ap-list" style="max-height:240px;overflow:auto;border:1px solid var(--line);border-radius:8px;margin-top:8px">
          ${avail.map((p) => `<label class="pick" data-name="${esc((p.name + " " + p.phone).toLowerCase())}" data-seg="${esc(p.segment)}" style="display:flex;gap:10px;align-items:center;padding:7px 12px;margin:0;font-weight:500;border-bottom:1px solid var(--line)">
            <input type="checkbox" name="pid" value="${p.id}" style="width:auto"><span>${esc(p.name)} <span class="muted small">${esc(p.phone)}${p.segment ? " · " + esc(p.segment) : ""}</span></span></label>`).join("")}</div>
          <div><label for="ap-msg" style="margin-top:10px">Personal message for the people you select (optional)</label>
          <textarea id="ap-msg" name="msg_pick" style="min-height:70px" placeholder="Leave empty to use the campaign script. Example: Hi {first_name}, we saved you a seat. Will you come?"></textarea><div class="hint">${varsHint}. You can also personalise one person at a time afterwards.</div></div>`
          : `<div class="empty"><p>Everyone on the event list who may be called is already in this campaign.<br>Use “New person” or “Import CSV” to add more.</p></div>`}
      </section>
      <section data-s="new" hidden><div class="form">
        <div class="two">${field("name", "Name", "")}${field("phone", "Mobile number", "", "placeholder=\"98765 43210\"")}</div>
        <div class="two">${select("language", "Call language", { "": "Use campaign language", ...META.languages }, "")}${field("segment", "Segment / group", "")}</div>
        <div><label for="n-msg">Personal message in this campaign (optional)</label><textarea id="n-msg" name="msg_new" style="min-height:70px" placeholder="Leave empty to use the campaign script"></textarea><div class="hint">${varsHint}</div></div>
        <label class="switch"><input type="checkbox" name="can_call" checked> OK to call this person</label>
        <div><label for="n-extra">Extra fields (optional, one per line as key=value)</label><textarea id="n-extra" name="extra" style="min-height:52px" placeholder="amount=Rs 5000"></textarea></div></div></section>
      <section data-s="csv" hidden><div class="form">
        <p class="muted small" style="margin:0">Header row required. <b>name</b>, <b>phone</b> required; optional <b>language</b>, <b>segment</b>, <b>message</b> (that person's own message in <i>this</i> campaign). <b>consent</b> (yes/no, default yes: “no” people are never called). Any other column, e.g. <b>amount</b>, becomes <code>{amount}</code>. People already on the event list are reused.</p>
        <div><label for="f_file">CSV file</label><input id="f_file" type="file" accept=".csv,text/csv,.txt"></div>
        <div><label for="f_csv">…or paste rows</label><textarea id="f_csv" name="csv" style="min-height:120px;font-family:ui-monospace,Consolas,monospace;font-size:13px" placeholder="name,phone,message&#10;Asha Rao,9876543210,Hi {first_name} we saved you a seat. Will you come?"></textarea></div></div></section>
    </div>`, { wide: true, submit: "Add to campaign", onSubmit: async (d, form) => {
      const base = `/campaigns/${state.c.id}`;
      let r;
      if (d.mode === "pick") {
        const ids = [...form.querySelectorAll("input[name=pid]:checked")].map((i) => +i.value);
        if (!ids.length) throw new Error("Tick at least one person");
        r = await api(base + "/members", { method: "POST", body: { participant_ids: ids, message: d.msg_pick || "" } });
        toast(`${r.added} added to the campaign`);
      } else if (d.mode === "new") {
        if (!d.name.trim() || !d.phone.trim()) throw new Error("Name and mobile number are required");
        const fields = {}; d.extra.split("\n").forEach((l) => { const i = l.indexOf("="); if (i > 0) fields[l.slice(0, i).trim()] = l.slice(i + 1).trim(); });
        await api(base + "/people", { method: "POST", body: { name: d.name, phone: d.phone, language: d.language, segment: d.segment, fields, can_call: d.can_call === "on", message: d.msg_new || "" } });
        toast("Person added to the campaign");
      } else {
        if (!d.csv.trim()) throw new Error("Choose a file or paste some rows");
        r = await api(base + "/import", { method: "POST", body: { csv: d.csv } });
        toast(`${r.added} added` + (r.error_count ? `, ${r.error_count} skipped (${r.errors.slice(0, 2).map((e) => `row ${e.row}: ${e.error}`).join("; ")})` : ""), r.added === 0);
      }
      people = await api(`/events/${c.event_id}/participants`);
      await refresh(true);
    } });
    const form = m.form;
    form.querySelectorAll("#ap-tabs button").forEach((b) => (b.onclick = () => {
      form.querySelector("[name=mode]").value = b.dataset.m;
      form.querySelectorAll("#ap-tabs button").forEach((x) => x.classList.toggle("active", x === b));
      form.querySelectorAll("section[data-s]").forEach((s) => (s.hidden = s.dataset.s !== b.dataset.m));
    }));
    const filterList = () => {
      const q = (form.querySelector("#ap-search")?.value || "").toLowerCase(), seg = form.querySelector("#ap-seg")?.value || "";
      form.querySelectorAll(".pick").forEach((l) => (l.hidden = !(l.dataset.name.includes(q) && (!seg || l.dataset.seg === seg))));
    };
    form.querySelector("#ap-search")?.addEventListener("input", filterList);
    form.querySelector("#ap-seg")?.addEventListener("change", filterList);
    form.querySelector("#ap-all")?.addEventListener("change", (e) => form.querySelectorAll(".pick:not([hidden]) input").forEach((i) => (i.checked = e.target.checked)));
    form.querySelector("#f_file").onchange = async (e) => { const f = e.target.files[0]; if (f) form.querySelector("#f_csv").value = await f.text(); };
  }

  // ---- one person's own message in this campaign
  function editMessage(x) {
    const m = modal(`Message for ${x.participant_name}`, `<div class="form">
      <div><label for="em">What ${esc(x.participant_name.split(" ")[0])} hears in “${esc(state.c.name)}” (leave empty for the campaign script)</label>
        <textarea id="em" name="message" style="min-height:110px" placeholder="Hi {first_name}, ...">${esc(x.custom_message)}</textarea>
        <div class="vars" id="em-vars">${META.variables.map((v) => `<button type="button" data-v="${esc(v)}">{${esc(v)}}</button>`).join("")}</div></div>
      <div class="preview" id="em-pv" aria-live="polite"></div>
      <div class="hint">This message applies to this campaign only. The same person can have a different message in another campaign.</div></div>`,
      { submit: "Save message", onSubmit: async (d) => {
        await api("/calls/" + x.id, { method: "PATCH", body: { message: d.message } });
        toast(d.message.trim() ? "Personal message saved" : "Using the campaign script"); await refresh(true); previewFn();
      } });
    const ta = m.form.querySelector("#em");
    const pv = guard(async () => {
      const r = await api(`/campaigns/${state.c.id}/preview`, { method: "POST", body: { participant_id: x.participant_id, message: ta.value } });
      m.form.querySelector("#em-pv").innerHTML = `<div class="who">${esc(META.languages[r.language])}</div>${esc(r.text)}${r.missing.length ? `<div class="warn-text">No value for ${r.missing.map((v) => "{" + esc(v) + "}").join(", ")}: that part will be left out.</div>` : ""}`;
    });
    let t; ta.oninput = () => { clearTimeout(t); t = setTimeout(pv, 250); };
    m.form.querySelector("#em-vars").onclick = (e) => { const v = e.target.dataset.v; if (v) { ta.setRangeText(`{${v}}`, ta.selectionStart, ta.selectionEnd, "end"); ta.focus(); pv(); } };
    pv();
  }

  function results() {
    const cur = state.c;
    const groups = { all: () => true, attention: (x) => NON_RESPONDER.includes(x.outcome) || x.needs_review, confirmed: (x) => x.outcome === "confirmed",
      declined: (x) => ["declined", "opted_out"].includes(x.outcome), pending: (x) => isActive(x) };
    const names = { all: "All", attention: "Needs attention", confirmed: "Confirmed", declined: "Declined", pending: "Not finished" };
    const rows = cur.calls.filter(groups[filter]);
    const msgCell = (x) => x.message ? `${x.custom_message ? `<span class="tag-review" style="color:var(--accent)">personal</span> ` : ""}${esc(x.message)}`
      : x.custom_message ? `<span class="tag-review" style="color:var(--accent)">personal</span> ${esc(x.custom_message)}` : `<span class="muted">Campaign script</span>`;
    $("#results").innerHTML = `<h2>People in this campaign</h2>
      <div class="filter">${Object.keys(groups).map((k) => `<button data-f="${k}" class="${k === filter ? "active" : ""}">${names[k]} (${cur.calls.filter(groups[k]).length})</button>`).join("")}</div>
      ${rows.length ? `<div class="table-wrap"><table><thead><tr><th>Person</th><th>Segment</th><th>Language</th><th>Outcome</th><th>Attempts</th><th>Message</th><th></th></tr></thead><tbody>
        ${rows.map((x) => `<tr><td>${esc(x.participant_name)}<div class="muted small">${esc(x.phone)}</div></td><td>${esc(x.segment || "—")}</td><td>${esc(META.languages[x.language] || x.language)}</td>
          <td>${pill(x.outcome)}${x.needs_review ? ` <span class="tag-review">review</span>` : ""}${x.next_attempt_at ? `<div class="muted small">Next try about ${esc(when(x.next_attempt_at))}</div>` : ""}${x.time_hint ? `<div class="muted small">Prefers: ${esc(x.time_hint)}</div>` : ""}${x.error ? `<div class="small" style="color:var(--bad)">${esc(x.error)}</div>` : ""}${x.blocked ? `<div class="small" style="color:var(--bad)">${esc(x.blocked)}: will not be called</div>` : ""}</td>
          <td>${x.attempts}/${cur.max_attempts}</td><td class="msg-cell" title="${esc(x.message || x.custom_message)}">${msgCell(x)}</td>
          <td class="nowrap" style="text-align:right">
            ${x.outcome === "in_progress" ? "" : `<button class="btn sm" data-msg="${x.id}">Message</button>`}
            ${x.outcome === "pending" ? `<button class="btn sm danger" data-rm="${x.id}">Remove</button>` : ""}
            ${isActive(x) || x.opted_out ? "" : `<button class="btn sm" data-redial="${x.id}">Call again</button>`}</td></tr>`).join("")}</tbody></table></div>`
        : `<div class="empty"><h3>${cur.calls.length ? "Nothing here" : "Nobody in this campaign yet"}</h3><p>${cur.calls.length ? "No one matches this filter." : "Add people from the event's list, a new person, or a CSV. Then press “Start calls” and each person hears their own message."}</p>
          ${cur.calls.length ? "" : `<button class="btn primary" id="empty-add">＋ Add people</button>`}</div>`}`;
    const R = $("#results");
    R.querySelectorAll("[data-f]").forEach((b) => (b.onclick = () => { filter = b.dataset.f; results(); }));
    R.querySelectorAll("[data-redial]").forEach((b) => (b.onclick = guard(async () => { await api(`/calls/${b.dataset.redial}/redial`, { method: "POST" }); toast("Calling…"); refresh(); })));
    R.querySelectorAll("[data-msg]").forEach((b) => (b.onclick = () => editMessage(state.c.calls.find((x) => x.id == b.dataset.msg))));
    R.querySelectorAll("[data-rm]").forEach((b) => (b.onclick = guard(async () => { await api("/calls/" + b.dataset.rm, { method: "DELETE" }); toast("Removed from campaign"); refresh(true); })));
    const ea = $("#empty-add"); if (ea) ea.onclick = addPeople;
  }

  function editor() {
    const cur = state.c;
    $("#editor").innerHTML = `<h2>What the call says</h2>
      <div class="grid g2">
        <div><label for="tpl">Call script <span class="muted" style="font-weight:400">(used for everyone in this campaign without a personal message)</span></label>
          <textarea id="tpl" style="min-height:150px">${esc(cur.template)}</textarea>
          <div class="vars" id="vars">${META.variables.map((v) => `<button type="button" data-v="${esc(v)}">{${esc(v)}}</button>`).join("")}</div>
          <div class="hint">Click a variable to insert it. Each person hears their own name and the event details. Set a personal message for one person with “Message” in the table below. If you keep the suggested script, people set to another language get it in their language; if you edit it, everyone hears your wording.</div>
          <div class="actions" style="margin-top:12px"><button class="btn primary" id="save-tpl">Save script</button><button class="btn" id="reset-tpl">Reset to suggested</button></div></div>
        <div><label for="pv-person">Preview for</label>
          <select id="pv-person" style="margin-bottom:10px"></select>
          <div class="preview" id="pv" aria-live="polite"></div>
          <div class="hint">The agent listens for a spoken reply or keypad: 1 = yes, 2 = no, 3 = call me later, 4 = need information, 9 = do not call again.</div></div></div>`;
    const tpl = $("#tpl"), sel = $("#pv-person");
    const fillSelect = () => {
      const keep = sel.value;
      sel.innerHTML = `<option value="">Sample person</option>` + state.c.calls.map((x) => `<option value="${x.participant_id}">${esc(x.participant_name)}${x.custom_message ? " (personal message)" : ""}</option>`).join("");
      sel.value = keep;
    };
    fillSelect();
    const doPreview = guard(async () => {
      fillSelect();
      const r = await api(`/campaigns/${state.c.id}/preview`, { method: "POST", body: { template: tpl.value, participant_id: sel.value ? +sel.value : null } });
      $("#pv").innerHTML = `<div class="who">${esc(r.participant || "Sample")} · ${esc(META.languages[r.language])}</div>${esc(r.text)}${r.missing.length ? `<div class="warn-text">No value for ${r.missing.map((m) => "{" + esc(m) + "}").join(", ")} for this person: that part will be left out.</div>` : ""}`;
    });
    previewFn = doPreview;
    let t; tpl.oninput = () => { clearTimeout(t); t = setTimeout(doPreview, 250); };
    sel.onchange = doPreview;
    $("#vars").onclick = (e) => { const v = e.target.dataset.v; if (!v) return; tpl.setRangeText(`{${v}}`, tpl.selectionStart, tpl.selectionEnd, "end"); tpl.focus(); doPreview(); };
    $("#save-tpl").onclick = guard(async () => {
      const cu = state.c;
      await api("/campaigns/" + cu.id, { method: "PATCH", body: { name: cu.name, purpose: cu.purpose, language: cu.language, max_attempts: cu.max_attempts, auto_retry: cu.auto_retry, retry_interval_min: cu.retry_interval_min, template: tpl.value } });
      toast("Script saved. It applies to calls not yet made."); await refresh();
    });
    $("#reset-tpl").onclick = guard(async () => {
      const r = await api(`/templates?event_type=${ev.type}&purpose=${cur.purpose}&language=${cur.language}`); tpl.value = r.template; doPreview();
    });
    doPreview();
  }

  async function refresh(membersChanged) {
    state.c = await api("/campaigns/" + id); head(); results(); refreshTaskCount();
    if (membersChanged) previewFn();
    clearTimeout(pollTimer);
    if (state.c.state === "running" && location.hash === "#/campaigns/" + id) pollTimer = setTimeout(() => refresh(), 2000);
  }
  head(); editor(); results();
  if (c.state === "running") pollTimer = setTimeout(() => refresh(), 2000);
}

// ---------------------------------------------------------------- shared small helpers
function rsvpLabel(r) {
  const t = { attending: "Attending", not_attending: "Not attending", undecided: "Undecided" }[r];
  return t ? `<span class="rsvp-${r}">${t}</span>` : `<span class="muted">No answer yet</span>`;
}
async function refreshTaskCount() {
  try {
    const n = (await api("/tasks")).length, el = $("#task-count");
    el.hidden = !n; el.textContent = n;
  } catch (e) { /* the badge is a convenience only */ }
}

// ---------------------------------------------------------------- settings
async function settings() {
  const st = await api("/settings"), h = st.calling_hours;
  app.innerHTML = `
    <div class="page-head"><div><h1>Settings</h1><div class="muted">Rules that apply to every campaign</div></div></div>
    <form class="card" id="hours-form" style="max-width:720px">
      <h2>Calling hours</h2>
      <p class="muted" style="margin-top:-6px">Only place calls between these times, in ${esc(st.timezone)}, so people are not phoned at night. Switch it off to test at any time of day.</p>
      <div id="hours-banner" class="banner" style="margin-bottom:14px"></div>
      <label class="switch" style="margin-bottom:14px"><input type="checkbox" id="h-on" ${h.enabled ? "checked" : ""}> Only call during these hours</label>
      <div id="h-times" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;max-width:360px">
        <div><label for="h-start">From</label><input id="h-start" type="time" value="${esc(h.start)}"></div>
        <div><label for="h-end">Until</label><input id="h-end" type="time" value="${esc(h.end)}"></div></div>
      ${st.simulated ? `<p class="hint">Demo mode is on: simulated calls ignore calling hours.</p>` : ""}
      <div class="actions" style="margin-top:16px"><button class="btn primary" type="submit">Save</button></div>
    </form>`;
  const on = $("#h-on"), banner = $("#hours-banner");
  const paint = () => {
    $("#h-times").style.opacity = on.checked ? 1 : .45;
    $("#h-start").disabled = $("#h-end").disabled = !on.checked;
    if (!on.checked) { banner.className = "banner warn"; banner.textContent = `Calling hours are OFF. Calls can be placed at any time (it is ${st.now_local} IST now).`; return; }
    const inside = $("#h-start").value <= st.now_local && st.now_local <= $("#h-end").value;
    banner.className = "banner " + (inside ? "good" : "warn");
    banner.textContent = inside ? `It is ${st.now_local} IST: inside the allowed window, calls can go out now.` : `It is ${st.now_local} IST: outside the allowed window, so calls will be refused until it opens.`;
  };
  on.onchange = paint; $("#h-start").oninput = paint; $("#h-end").oninput = paint; paint();
  $("#hours-form").onsubmit = guard(async (e) => {
    e.preventDefault();
    await api("/settings/calling-hours", { method: "PUT", body: { enabled: on.checked, start: $("#h-start").value, end: $("#h-end").value } });
    toast(on.checked ? "Calling hours saved" : "Calling hours switched off"); settings();
  });
}

// ---------------------------------------------------------------- follow-ups
async function followups() {
  const status = sessionStorage.getItem("task-status") || "open";
  const [tasks, evs] = await Promise.all([api("/tasks?status=" + status), api("/events")]);
  const evFilter = sessionStorage.getItem("task-event") || "";
  const rows = tasks.filter((t) => !evFilter || String(t.event_id) === evFilter);
  const KIND = { in_person_call: "Call / meet in person", callback: "Call back", answer_question: "Answer a question" };
  app.innerHTML = `
    <div class="page-head"><div><h1>Follow-ups</h1><div class="muted">People the automated call could not settle, waiting for a human</div></div>
      <div class="actions"><select id="t-event" style="width:auto"><option value="">All events</option>${evs.map((e) => `<option value="${e.id}" ${String(e.id) === evFilter ? "selected" : ""}>${esc(e.name)}</option>`).join("")}</select></div></div>
    <div class="tabs"><button data-st="open" class="${status === "open" ? "active" : ""}">To do</button><button data-st="done" class="${status === "done" ? "active" : ""}">Done</button></div>
    <div class="card">${rows.length ? rows.map((t) => `
      <div class="task"><div>
        <span class="kind">${esc(KIND[t.kind] || t.kind)}</span>
        <div><b>${esc(t.participant_name)}</b> · <a href="tel:${esc(t.phone)}">${esc(t.phone)}</a> · ${rsvpLabel(t.rsvp)}</div>
        <div class="reason">${esc(t.reason)}</div>
        <div class="muted small">${esc(t.event_name)}${t.campaign_name ? ` · <a href="#/campaigns/${t.campaign_id}">${esc(t.campaign_name)}</a>` : ""}${t.note ? ` · Note: ${esc(t.note)}` : ""}</div></div>
        <div class="actions">${status === "open"
          ? `<button class="btn sm" data-done="${t.id}" data-rsvp="attending">Coming</button><button class="btn sm" data-done="${t.id}" data-rsvp="not_attending">Not coming</button><button class="btn sm" data-done="${t.id}" data-rsvp="">Done</button>`
          : `<button class="btn sm" data-reopen="${t.id}">Reopen</button>`}</div></div>`).join("")
      : `<div class="empty"><h3>${status === "open" ? "Nothing to follow up" : "Nothing completed yet"}</h3><p>${status === "open" ? "When a call is unclear, someone asks to be called back, or a person cannot be reached, a task appears here." : ""}</p></div>`}</div>`;
  $("#t-event").onchange = (e) => { sessionStorage.setItem("task-event", e.target.value); followups(); };
  app.querySelectorAll("[data-st]").forEach((b) => (b.onclick = () => { sessionStorage.setItem("task-status", b.dataset.st); followups(); }));
  app.querySelectorAll("[data-done]").forEach((b) => (b.onclick = guard(async () => {
    const note = prompt("Add a note about what happened (optional)", "");
    if (note === null) return;
    await api("/tasks/" + b.dataset.done, { method: "PATCH", body: { status: "done", note, rsvp: b.dataset.rsvp || null } });
    toast("Marked done"); followups(); refreshTaskCount();
  })));
  app.querySelectorAll("[data-reopen]").forEach((b) => (b.onclick = guard(async () => {
    await api("/tasks/" + b.dataset.reopen, { method: "PATCH", body: { status: "open" } }); toast("Reopened"); followups(); refreshTaskCount();
  })));
}
