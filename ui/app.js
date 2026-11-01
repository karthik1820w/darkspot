"use strict";
const $ = id => document.getElementById(id);
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
let last = null;
function status(msg, err) { const s = $("status"); s.textContent = msg; s.className = err ? "err" : ""; }

function progress(stage, msg) {
  document.querySelectorAll("#prog li").forEach(li => { const n = +li.dataset.s; li.className = n < stage ? "done" : n === stage ? "on" : ""; });
  status(msg);
}
function quote(c) {
  const d = el("div", "q"), h = el("b", "", c.source_name + " [" + c.authority + "]" + (c.undated ? " (no visible date)" : c.stale ? " (older or past-dated)" : "") + (c.neg ? " (negated or optional wording)" : ""));
  const p = el("span", "ctx");
  p.append("…" + c.before + " "); p.append(Object.assign(el("mark"), { textContent: c.quote })); p.append(" " + c.after + "…");
  d.append(h, p); return d;
}
function lane(cls, title) { const d = el("div", "lane " + cls); d.append(el("h5", "", title)); return d; }
function item(it) {
  const d = el("details", "item " + it.state), s = el("summary"), b = el("div");
  s.append(el("span", "chip " + it.state, it.chip));
  b.append(el("h4", "", it.label), el("p", "", it.summary)); s.append(b); d.append(s);
  const ev = el("div", "ev");
  const dv = lane("derived", "Derived by code from the quotes");
  dv.append(el("p", "", "Confidence: " + it.confidence + " (" + it.confidence_why + "). Confidence is a rule-of-thumb, not a probability."));
  ev.append(dv);
  const so = lane("sourced", "Sourced: verbatim from the pages");
  const grid = el("div", it.state === "conflict" && it.claims.length > 1 ? "evgrid" : "");
  if (it.claims.length) it.claims.forEach(c => grid.append(quote(c))); else grid.append(el("p", "", "No supporting quote exists. This is a gap in the pages reviewed, not proof the information doesn’t exist."));
  so.append(grid); ev.append(so);
  const su = lane("suggested", "Suggested next step (not from the sources)");
  su.append(el("p", "", "Verify: " + it.verify)); if (it.ask) su.append(el("p", "", it.ask)); ev.append(su);
  d.append(ev); return d;
}
function render(r) {
  last = r; $("out").hidden = false; $("vt").textContent = r.verdict; $("vn").textContent = r.note;
  const m = r.meter; $("meter").max = m.total; $("meter").value = m.found;
  $("mt").textContent = m.found + " of " + m.total + " expected items found in the pages; " + m.corroborated + " confirmed by two or more pages. Checklist from: " + r.checklist_origin + ".";
  $("items").replaceChildren(...r.items.map(item));
  $("ok").replaceChildren(...(r.confirmed.length ? [el("span", "chip confirmed", "Confirmed"), document.createTextNode(" " + r.confirmed.map(c => c.label + ": " + c.claims[0].display + " (" + c.confidence + " confidence)").join("; "))] : []));
  $("src").replaceChildren(...r.sources.map(s => {
    const c = el("div", "card"), t = el("b", "", s.name);
    const info = s.error ? s.error : s.date ? "dated " + s.date + " (" + s.date_method + ")" : "no visible date";
    c.append(t, el("span", "auth", "  [" + s.authority + (s.url ? ", guessed from domain" : ", user-supplied") + "]"), el("span", "", "  " + info));
    if (s.stale) c.append(el("span", "warn", "  Older than a year"));
    if (s.injection) c.append(el("span", "warn", "  Contains instruction-like text; treated as data only"));
    if (s.truncated) c.append(el("span", "warn", "  Long page, only the start was read"));
    return c;
  }));
  $("out").scrollIntoView({ behavior: "smooth" });
}
function busy(on) { document.querySelectorAll("button").forEach(b => b.disabled = on); }
async function go(body) {
  busy(true); $("out").hidden = true; $("prog").hidden = false; progress(1, "Starting…");
  try {
    const res = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok) throw new Error((await res.json()).error || "Request failed.");
    const rd = res.body.getReader(), dec = new TextDecoder(); let buf = "", done = false;
    for (;;) {
      const { value, done: end } = await rd.read(); if (end) break;
      buf += dec.decode(value, { stream: true }); let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (!line) continue;
        const ev = JSON.parse(line);
        if (ev.error) throw new Error(ev.error);
        if (ev.done) { done = true; document.querySelectorAll("#prog li").forEach(li => li.className = "done"); status(""); render(ev.done); }
        else progress(ev.stage, ev.msg);
      }
    }
    if (!done) throw new Error("The connection ended before results arrived.");
  } catch (e) { status(e.message, true); }
  busy(false);
}
const readPdf = f => new Promise((ok, no) => {
  if (f.size > 600000) return no(new Error(f.name + " is over 600 KB."));
  const r = new FileReader(); r.onload = () => ok({ name: f.name.slice(0, 60), b64: String(r.result).split(",")[1] }); r.onerror = () => no(new Error("Could not read " + f.name)); r.readAsDataURL(f);
});
$("f").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    const urls = $("u").value.split("\n").map(x => x.trim()).filter(Boolean);
    const texts = $("t").value.split(/^\s*---\s*$/m).map((x, i) => ({ name: "Pasted text " + (i + 1), text: x })).filter(x => x.text.trim());
    const pdfs = await Promise.all([...$("pdf").files].slice(0, 3).map(readPdf));
    go({ question: $("q").value, template: $("tpl").value, mode: $("mode").value, discover: $("disc").checked, urls, texts, pdfs });
  } catch (err) { status(err.message, true); }
});
$("demo").onclick = () => { $("q").value = "What should I verify before applying for the Aarohan Merit Scholarship?"; go({ sample: true, question: $("q").value }); };
$("print").onclick = () => window.print();
const text = () => [last.verdict, ...last.items.map(i => `[${i.chip}] ${i.label}: ${i.summary} Verify: ${i.verify}`)].join("\n");
$("copy").onclick = async () => { if (!last) return; try { await navigator.clipboard.writeText(text()); status("Checklist copied."); } catch { status("Copy failed. Select the text and copy it.", true); } };
$("md").onclick = () => {
  if (!last) return;
  const md = ["# DarkSpot report", "", "Question: " + last.question, "", "**" + last.verdict + "**", "", last.note, "",
    ...last.items.flatMap(i => ["## " + i.chip + ": " + i.label, i.summary, "", ...i.claims.map(c => "> " + c.quote + " (" + c.source_name + ", " + c.authority + ")"), "", "Suggested (not sourced): " + i.verify, ""]),
    "## Sources", ...last.sources.map(s => "- " + s.name + " [" + s.authority + "] " + (s.date || "no date"))].join("\n");
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([md], { type: "text/markdown" })); a.download = "darkspot-report.md"; a.click(); URL.revokeObjectURL(a.href);
};
