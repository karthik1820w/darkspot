"use strict";
const $ = id => document.getElementById(id);
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
let last = null;
const status = (msg, err) => { const s = $("status"); s.textContent = msg; s.className = err ? "err" : ""; };
const busy = on => { document.querySelectorAll("button").forEach(b => b.disabled = on); $("out").setAttribute("aria-busy", String(on)); };
function progress(stage, msg) {
  document.querySelectorAll("#prog li").forEach(li => { const n = +li.dataset.s; li.className = n < stage ? "done" : n === stage ? "on" : ""; n === stage ? li.setAttribute("aria-current", "step") : li.removeAttribute("aria-current"); });
  status(msg);
}
/* Each stage is its own short, stateless request (works on serverless; no long-lived connection needed). */
async function api(path, body) {
  let res;
  try { res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }
  catch { throw new Error("Could not reach the server."); }
  const d = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(d.error || "Request failed (" + res.status + ").");
  return d;
}
const keyOf = q => "ds:" + q.trim().toLowerCase().slice(0, 100);
const loadPrev = q => { try { return JSON.parse(localStorage.getItem(keyOf(q))); } catch { return null; } };
const savePrev = (q, s) => { try { localStorage.setItem(keyOf(q), JSON.stringify(s)); } catch { /* storage unavailable: skip */ } };

function quote(c) {
  const d = el("div", "q"), h = el("b", "", c.source_name);
  h.append(el("span", "badge " + c.authority, c.authority));
  [c.undated ? "no visible date" : c.stale ? "older or past-dated" : "", c.neg ? "negated or optional wording" : ""].filter(Boolean).forEach(f => h.append(el("span", "flag", f)));
  const p = el("span", "ctx");
  p.append("…" + c.before + " "); p.append(Object.assign(el("mark"), { textContent: c.quote })); p.append(" " + c.after + "…");
  d.append(h, p); return d;
}
function lane(cls, title) { const d = el("div", "lane " + cls); d.append(el("h5", "", title)); return d; }
function item(it) {
  const d = el("details", "item " + it.state), s = el("summary"), b = el("div");
  s.append(el("span", "chip " + it.state, it.chip));
  const h4 = el("h4", "", it.label); if (it.impact) h4.append(el("span", "impact", "+" + it.impact + " pts if resolved")); b.append(h4, el("p", "", it.summary)); s.append(b); d.append(s);
  const ev = el("div", "ev"), dv = lane("derived", "Derived by code from the quotes");
  dv.append(el("p", "", "Confidence: " + it.confidence + " (" + it.confidence_why + "). A rule of thumb, not a probability.")); ev.append(dv);
  const so = lane("sourced", "Sourced: verbatim from the pages"), grid = el("div", it.state === "conflict" && it.claims.length > 1 ? "evgrid" : "");
  if (it.claims.length) it.claims.forEach(c => grid.append(quote(c))); else grid.append(el("p", "", "No supporting quote exists. This is a gap in the pages reviewed, not proof the information doesn’t exist."));
  so.append(grid); ev.append(so);
  if (it.caveats && it.caveats.length) { const cv = lane("caveat", "The page itself hedges"); it.caveats.forEach(h => { const p = el("p", "", h.source_name + " (" + h.kind.toLowerCase() + "): "); p.append(el("em", "", "“" + h.quote + "”")); cv.append(p); }); ev.append(cv); }
  const su = lane("suggested", "Suggested next step (not from the sources)");
  su.append(el("p", "", "Verify: " + it.verify)); if (it.ask) su.append(el("p", "", it.ask)); ev.append(su);
  d.append(ev); return d;
}
function extras(r) {
  const p = r.readiness.path || [];
  $("path").textContent = p.length ? "Fastest route: verify " + p.map(x => x.label.toLowerCase() + " (+" + x.gain + ")").join(", then ") + " → readiness " + r.readiness.pct + "% → " + p[p.length - 1].after + "%. A what-if on the rule below, not a prediction." : "";
  const c = r.cycles, cy = $("cyc"); cy.hidden = !(c && (c.drift.length || c.unstated.length));
  const kids = [];
  if (c && c.drift.length) { kids.push(el("h3", "", "Earlier application cycle detected")); c.drift.forEach(d => { const p = el("p", "", d.source_name + " is about " + d.label + ", but the newest page covers " + d.newest_label + ". Its details are treated as possibly outdated. "); p.append(el("em", "", "“" + d.quote + "”")); kids.push(p); }); }
  if (c && c.unstated.length) kids.push(el("p", "small", "No cycle or year range is stated on: " + c.unstated.map(u => u.source_name).join(", ") + ". Check which cycle it describes."));
  cy.replaceChildren(...kids);
  $("qs").replaceChildren(...r.questions.map(q => el("li", "", q.question)));
  $("qh").hidden = $("qs").hidden = !r.questions.length;
  $("hedw").hidden = !r.hedges.length;
  $("hed").replaceChildren(...r.hedges.map(h => { const d = el("div", "q"), b = el("b", "", h.source_name); b.append(el("span", "badge " + h.authority, h.authority), el("span", "flag", h.kind + (h.label ? " · " + h.label : ""))); const t = el("span", "ctx"); t.append(Object.assign(el("mark"), { textContent: h.quote })); d.append(b, t); return d; }));
}
function overview(o) {
  const t = $("ov"), head = el("tr"), body = el("tbody");
  head.append(Object.assign(el("th", "", "Item"), { scope: "col" }));
  o.sources.forEach(s => { const h = el("th", "", s.name); h.scope = "col"; h.append(el("span", "badge " + s.authority, s.authority)); head.append(h); });
  o.rows.forEach(r => {
    const tr = el("tr"), th = el("th", "", r.label); th.scope = "row"; th.append(el("span", "chip " + r.state, r.chip)); tr.append(th);
    o.sources.forEach(s => {
      const td = el("td"), cs = r.cells[s.id] || [];
      if (!cs.length) td.append(el("span", "nf", "Not found"));
      cs.forEach(c => { const d = el("div", "cell"); d.append(el("div", "cv", c.text)); if (c.text !== c.quote) d.append(el("div", "cq", "“" + c.quote + "”")); if (c.flags.length) d.append(el("div", "flag", c.flags.join(", "))); td.append(d); });
      tr.append(td);
    });
    body.append(tr);
  });
  t.replaceChildren(el("thead"), body); t.firstChild.append(head);
}
function render(r) {
  last = r; $("out").hidden = false; $("vt").textContent = r.verdict; $("vn").textContent = r.note;
  const band = r.readiness.pct >= 85 ? "high" : r.readiness.pct >= 50 ? "mid" : "low";
  $("verdict").className = "verdict " + band; $("gauge").className = "gauge " + band; $("gauge").style.setProperty("--p", r.readiness.pct);
  $("gauge").setAttribute("aria-label", "Decision readiness " + r.readiness.pct + " percent");
  $("rdp").textContent = r.readiness.pct + "%"; $("rdb").textContent = "Decision readiness: " + r.readiness.band; $("rdr").textContent = r.readiness.rule;
  const all = r.items.concat(r.confirmed), tl = [];
  for (const st of ["conflict", "gap", "check", "stale", "single", "confirmed"]) { const m = all.filter(i => i.state === st); if (m.length) { const li = el("li"); li.append(el("span", "chip " + st, m.length + " " + m[0].chip.toLowerCase())); tl.push(li); } }
  $("tally").replaceChildren(...tl);
  const m = r.meter; $("meter").max = m.total; $("meter").value = m.found;
  $("mt").textContent = m.found + " of " + m.total + " expected items found; " + m.corroborated + " confirmed by two or more independent pages. Checklist from: " + r.checklist_origin + ".";
  $("chg").hidden = !(r.changes && r.changes.length); $("chgl").replaceChildren(...(r.changes || []).map(c => el("li", "", c)));
  $("dup").hidden = !r.duplicates.length;
  $("dup").replaceChildren(...(r.duplicates.length ? [el("b", "", "Possible copies: "), document.createTextNode(r.duplicates.map(g => g.join(" and ")).join("; ") + " share mostly identical text, so they count as one source, not independent confirmation.")] : []));
  overview(r.overview); extras(r);
  $("items").replaceChildren(...r.items.map(item)); const f = $("items").querySelector("details"); if (f) f.open = true;
  $("expand").textContent = "Expand all"; $("expand").setAttribute("aria-expanded", "false"); $("expand").hidden = !r.items.length;
  const ul = el("ul"); r.confirmed.forEach(c => { const li = el("li"); li.append(el("b", "", "✓ " + c.label), document.createTextNode(c.claims[0].display + " · " + c.confidence + " confidence · " + c.summary.replace(/^Matches across /, "seen in ").replace(/: .*$/, ""))); ul.append(li); });
  $("ok").replaceChildren(...(r.confirmed.length ? [el("h3", "", "Confirmed by independent pages"), ul] : []));
  $("em").hidden = !r.email_draft; $("emt").textContent = r.email_draft;
  $("src").replaceChildren(...r.sources.map(s => {
    const c = el("div", "card");
    const info = s.error ? s.error : s.date ? "dated " + s.date + " (" + s.date_method + ")" : "no visible date";
    c.append(el("b", "", s.name), el("span", "auth", "  [" + s.authority + (s.url ? ", guessed from domain" : ", user-supplied") + "]"), el("span", "", "  " + info));
    if (s.hash) c.append(el("span", "auth", "  sha256 " + s.hash.slice(0, 10) + "… read " + s.retrieved_at));
    if (s.stale) c.append(el("span", "warn", "  Older than a year"));
    if (s.injection) c.append(el("span", "warn", "  Contains instruction-like text; treated as data only"));
    if (s.truncated) c.append(el("span", "warn", "  Long page, only the start was read"));
    return c;
  }));
  $("rc").textContent = "This check is saved in your browser. Run the same question again later to see what changed. " + r.independence.pages + " pages read, " + r.independence.independent + " independent (copies count once), " + r.independence.official + " look official. Report ID " + r.fingerprint.slice(0, 16) + ": it changes if any page or finding changes.";
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  $("out").scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" }); $("vt").focus({ preventScroll: true });
}
async function run(inp) {
  busy(true); $("out").hidden = true; $("plan").hidden = true; $("prog").hidden = false;
  try {
    progress(1, "Checking your question…");
    if (!inp.question.trim()) { $("q").setAttribute("aria-invalid", "true"); $("qerr").textContent = "Type the question you want answered first."; $("q").focus(); throw new Error("Enter a question."); }
    progress(2, "Building the expected-answer checklist…");
    const cl = await api("/api/checklist", { question: inp.question, template: inp.template, mode: inp.mode, discover: inp.discover });
    $("plan").hidden = false; $("plant").textContent = cl.items.map(i => i.label).join(", ") + ". Source: " + cl.origin + (cl.warning ? ". " + cl.warning : "") + ".";
    const tasks = [...inp.tasks, ...cl.urls.map(url => ({ url }))].slice(0, 6);
    if (!tasks.length) throw new Error("Add at least one link, PDF or pasted text" + (inp.discover ? " (search found nothing)." : "."));
    progress(3, "Collecting " + tasks.length + " source" + (tasks.length > 1 ? "s" : "") + " in parallel…"); let n = 0;
    const sources = await Promise.all(tasks.map((t, i) => api("/api/sources", { ...t, idx: i + 1 }).then(s => { progress(3, "Collected " + (++n) + " of " + tasks.length + ": " + s.name); return s; })));
    progress(4, "Extracting quotes, verifying each against the page text, comparing…");
    const res = await api("/api/analyze", { question: inp.question, checklist: cl, sources, mode: inp.mode, previous: loadPrev(inp.question) });
    document.querySelectorAll("#prog li").forEach(li => li.className = "done"); status("");
    savePrev(inp.question, res.snapshot); render(res);
  } catch (e) { status(e.message, true); }
  busy(false);
}
const readPdf = f => new Promise((ok, no) => {
  if (f.size > 600000) return no(new Error(f.name + " is over 600 KB."));
  const r = new FileReader(); r.onload = () => ok({ pdf: { name: f.name.slice(0, 60), b64: String(r.result).split(",")[1] } });
  r.onerror = () => no(new Error("Could not read " + f.name)); r.readAsDataURL(f);
});
$("f").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    const urls = $("u").value.split("\n").map(x => x.trim()).filter(Boolean).map(url => ({ url }));
    const texts = $("t").value.split(/^\s*---\s*$/m).map((x, i) => ({ name: "Pasted text " + (i + 1), text: x })).filter(x => x.text.trim());
    const pdfs = await Promise.all([...$("pdf").files].slice(0, 3).map(readPdf));
    run({ question: $("q").value, template: $("tpl").value, mode: $("mode").value, discover: $("disc").checked, tasks: [...urls, ...texts, ...pdfs] });
  } catch (err) { status(err.message, true); }
});
$("demo").onclick = () => { $("q").value = "What should I verify before applying for the Aarohan Merit Scholarship?"; run({ question: $("q").value, template: "scholarship", mode: "rules", tasks: [{ sample: 1 }, { sample: 2 }, { sample: 3 }] }); };
$("print").onclick = () => window.print();
const download = (name, type, data) => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([data], { type })); a.download = name; a.click(); URL.revokeObjectURL(a.href); };
const flash = (b, m) => { const o = b.textContent; b.textContent = m; setTimeout(() => b.textContent = o, 1600); };
const copy = async (t, b) => { try { await navigator.clipboard.writeText(t); flash(b, "Copied ✓"); } catch { status("Copy failed. Select the text and copy it.", true); } };
$("copy").onclick = () => last && copy([last.verdict, ...last.items.map(i => `[${i.chip}] ${i.label}: ${i.summary} Verify: ${i.verify}`)].join("\n"), $("copy"));
$("emc").onclick = () => last && copy(last.email_draft, $("emc"));
$("json").onclick = () => last && download("darkspot-evidence.json", "application/json", JSON.stringify({ question: last.question, checked: last.today, sources: last.sources, overview: last.overview, questions: last.questions, hedges: last.hedges, cycles: last.cycles, report_id: last.fingerprint, findings: last.items.concat(last.confirmed) }, null, 2));
$("md").onclick = () => last && download("darkspot-report.md", "text/markdown", ["# DarkSpot report", "", "Question: " + last.question, "", "**" + last.verdict + "** (readiness " + last.readiness.pct + "%)", "", last.note, "",
  ...last.items.flatMap(i => ["## " + i.chip + ": " + i.label, i.summary, "", ...i.claims.map(c => "> " + c.quote + " (" + c.source_name + ", " + c.authority + ")"), "", "Suggested (not sourced): " + i.verify, ""]),
  "## Questions the sources leave unanswered", ...last.questions.map((q, n) => (n + 1) + ". " + q.question), "", "Report ID: " + last.fingerprint, "",
  "## What the sources say", ...last.overview.rows.map(r => "- " + r.label + " [" + r.chip + "]: " + last.overview.sources.map(s => s.name + " = " + ((r.cells[s.id] || []).map(c => c.text).join(" | ") || "not found")).join("; ")), "",
  "## Sources", ...last.sources.map(s => "- " + s.name + " [" + s.authority + "] " + (s.date || "no date") + (s.hash ? " sha256:" + s.hash : ""))].join("\n"));

/* ---- interaction polish ---- */
$("q").addEventListener("input", () => { $("q").removeAttribute("aria-invalid"); $("qerr").textContent = ""; });
document.querySelectorAll(".chipbtn").forEach(b => b.onclick = () => { $("q").value = b.dataset.q; $("tpl").value = "auto"; $("q").dispatchEvent(new Event("input")); $("q").focus(); });
$("expand").onclick = () => { const open = $("expand").getAttribute("aria-expanded") !== "true"; $("items").querySelectorAll("details").forEach(d => d.open = open); $("expand").setAttribute("aria-expanded", String(open)); $("expand").textContent = open ? "Collapse all" : "Expand all"; };
const dz = $("drop");
["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("over"); }));
dz.addEventListener("drop", e => { const fs = [...e.dataTransfer.files].filter(f => f.type === "application/pdf"); if (!fs.length) return status("Only PDF files can be dropped here.", true); const dt = new DataTransfer(); fs.slice(0, 3).forEach(f => dt.items.add(f)); $("pdf").files = dt.files; status(fs.length + " PDF" + (fs.length > 1 ? "s" : "") + " ready."); });
addEventListener("beforeprint", () => document.querySelectorAll("#items details,#em").forEach(d => d.open = true));
