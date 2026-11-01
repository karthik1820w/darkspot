"use strict";
const $ = id => document.getElementById(id);
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
let last = null;
function status(msg, err) { const s = $("status"); s.textContent = msg; s.className = err ? "err" : ""; }

function quote(c) {
  const d = el("div", "q"), h = el("b", "", c.source_name + (c.undated ? " (no visible date)" : c.stale ? " (older or past-dated)" : ""));
  const p = el("span", "ctx");
  p.append("…" + c.before + " "); p.append(Object.assign(el("mark"), { textContent: c.quote })); p.append(" " + c.after + "…");
  d.append(h, p); return d;
}
function item(it) {
  const d = el("details", "item " + it.state), s = el("summary"), b = el("div");
  s.append(el("span", "chip " + it.state, it.chip));
  b.append(el("h4", "", it.label), el("p", "", it.summary), el("p", "v", "Verify: " + it.verify));
  s.append(b); d.append(s);
  const ev = el("div", "ev");
  if (it.claims.length) it.claims.forEach(c => ev.append(quote(c)));
  else ev.append(el("p", "", "No supporting quote exists. This is a gap in the pages reviewed, not proof the information doesn’t exist."));
  if (it.state === "conflict" || it.state === "stale" || it.state === "gap") ev.append(el("div", "hatch", "Potential " + it.chip.toLowerCase() + " (rule-based signal). Check the official source before relying on it."));
  d.append(ev); return d;
}
function render(r) {
  last = r; $("out").hidden = false; $("vt").textContent = r.verdict; $("vn").textContent = r.note;
  const L = $("items"); L.replaceChildren(...r.items.map(item));
  $("ok").replaceChildren(...(r.confirmed.length ? [el("span", "chip confirmed", "Confirmed"), document.createTextNode(" " + r.confirmed.map(c => c.label + ": " + c.claims[0].display).join("; "))] : []));
  $("src").replaceChildren(...r.sources.map(s => {
    const c = el("div", "card"), t = el("b", "", s.name);
    const info = s.error ? s.error : s.date ? "dated " + s.date + " (" + s.date_method + ")" : "no visible date";
    c.append(t, el("span", "", "  " + info));
    if (s.stale) c.append(el("span", "warn", "  Older than a year"));
    if (s.injection) c.append(el("span", "warn", "  Contains instruction-like text; treated as data only"));
    if (s.truncated) c.append(el("span", "warn", "  Long page, only the start was read"));
    return c;
  }));
  $("out").scrollIntoView({ behavior: "smooth" });
}
async function go(body) {
  document.querySelectorAll("button").forEach(b => b.disabled = true); status("Reading pages, quoting facts, comparing, checking for gaps…");
  try {
    const res = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Request failed.");
    status(""); render(data);
  } catch (e) { status(e.message, true); }
  document.querySelectorAll("button").forEach(b => b.disabled = false);
}
$("f").addEventListener("submit", e => {
  e.preventDefault();
  const urls = $("u").value.split("\n").map(x => x.trim()).filter(Boolean);
  const texts = $("t").value.split(/^\s*---\s*$/m).map((x, i) => ({ name: "Pasted text " + (i + 1), text: x })).filter(x => x.text.trim());
  go({ question: $("q").value, template: "scholarship", urls, texts });
});
$("demo").onclick = () => { $("q").value = "What should I verify before applying for the Aarohan Merit Scholarship?"; go({ sample: true, question: $("q").value }); };
$("print").onclick = () => window.print();
$("copy").onclick = async () => {
  if (!last) return;
  const lines = [last.verdict, ...last.items.map(i => `[${i.chip}] ${i.label}: ${i.summary} Verify: ${i.verify}`)].join("\n");
  try { await navigator.clipboard.writeText(lines); status("Checklist copied."); } catch { status("Copy failed. Select the text and copy it.", true); }
};
