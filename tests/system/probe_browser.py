import os, sys, time, subprocess, json
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("probe_browser: playwright not installed; skipping browser probes (pip install playwright && playwright install chromium)")
    sys.exit(0)
env = {**os.environ, "DARKSPOT_PORT": "8770", "DARKSPOT_RATE": "100000"}; srv = subprocess.Popen([sys.executable, "-m", "darkspot"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.2)
URL = "http://127.0.0.1:8770/"; RES = []
def case(id, title):
    def deco(fn):
        try: ok, d = fn()
        except Exception as e: ok, d = False, f"EXC {type(e).__name__}: {str(e)[:130]}"
        RES.append((id, ok, title, str(d)[:600])); return fn
    return deco
CONTRAST = """()=>{const lum=c=>{const [r,g,b]=c.map(v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)});return .2126*r+.7152*g+.0722*b};
const parse=s=>{const m=s.match(/[\\d.]+/g).map(Number);return {rgb:m.slice(0,3),a:m.length>3?m[3]:1}};
const bg=e=>{while(e){const p=parse(getComputedStyle(e).backgroundColor);if(p.a>0.5)return p.rgb;e=e.parentElement}return [255,255,255]};
const out=[];const seen=new Set();
for(const e of document.querySelectorAll("body *")){ if(!e.childNodes.length||![...e.childNodes].some(n=>n.nodeType==3&&n.textContent.trim()))continue; const cs=getComputedStyle(e); if(cs.visibility==="hidden"||e.closest("[hidden]")||cs.display==="none")continue;
 const k=cs.color+"|"+bg(e).join()+"|"+cs.fontSize; if(seen.has(k))continue; seen.add(k);
 const f=parse(cs.color).rgb,b=bg(e),L1=lum(f),L2=lum(b),r=(Math.max(L1,L2)+.05)/(Math.min(L1,L2)+.05);
 const px=parseFloat(cs.fontSize),big=px>=24||(px>=18.66&&+cs.fontWeight>=700); if(r<(big?3:4.5)) out.push(e.tagName.toLowerCase()+"."+e.className+" "+r.toFixed(2)+" ("+px+"px) '"+e.textContent.trim().slice(0,22)+"'")}
return out}"""
with sync_playwright() as p:
    b = p.chromium.launch()
    def page(**kw):
        ctx = b.new_context(**kw); pg = ctx.new_page(); pg.errs = []; pg.on("pageerror", lambda e: pg.errs.append(str(e))); pg.on("console", lambda m: pg.errs.append(m.text) if m.type == "error" else None); return pg
    def run_sample(pg): pg.goto(URL); pg.click("#demo"); pg.wait_for_selector("#out:not([hidden])", timeout=8000)

    @case("U01", "XSS: hostile markup in question and pasted page must render as inert text")
    def _():
        pg = page(); pg.goto(URL); pl = '<img src=x onerror=window.__x=1><script>window.__x=1</script>"><svg onload=window.__x=1>'
        pg.fill("#q", "deadline? " + pl); pg.fill("#t", "The deadline is 30 November 2026. " + pl + "\nThe fee is $350."); pg.click("button.primary"); pg.wait_for_selector("#out:not([hidden])", timeout=8000); pg.wait_for_timeout(400)
        injected = pg.evaluate("()=>document.querySelectorAll('#out img,#out svg,#out script,#plan img,#plan svg,#status img').length"); ex = pg.evaluate("()=>window.__x"); shown = "onerror" in pg.evaluate("document.querySelector('#items').textContent")   # inner_text skips collapsed <details>
        return injected == 0 and ex is None and shown, f"injected elements={injected}, executed={ex}, payload shown as text={shown}, errors={pg.errs[:1]}"
    @case("U02", "layout at 375px: no horizontal scrolling before or after a run (light and dark)")
    def _():
        bad = []
        for scheme in ("light", "dark"):
            pg = page(viewport={"width": 375, "height": 800}, color_scheme=scheme); pg.goto(URL); w0 = pg.evaluate("document.documentElement.scrollWidth"); pg.click("#demo"); pg.wait_for_selector("#out:not([hidden])"); pg.locator("#items details").first.evaluate("e=>e.open=true")
            w1 = pg.evaluate("document.documentElement.scrollWidth"); bad += [f"{scheme}:{w}px" for w in (w0, w1) if w > 375]
        return not bad, bad or "no overflow"
    @case("U03", "contrast (WCAG AA) of every visible text colour, light and dark, before and after a run")
    def _():
        out = {}
        for scheme in ("light", "dark"):
            pg = page(color_scheme=scheme); run_sample(pg); pg.locator("#items details").first.evaluate("e=>e.open=true"); out[scheme] = pg.evaluate(CONTRAST)
        return not (out["light"] or out["dark"]), out
    @case("U04", "keyboard only: type a question, Tab to the textarea, paste text, press Enter in the question field to submit")
    def _():
        pg = page(); pg.goto(URL); pg.fill("#t", "The deadline is 30 November 2026."); pg.focus("#q"); pg.keyboard.type("deadline?"); pg.keyboard.press("Enter"); pg.wait_for_selector("#out:not([hidden])", timeout=8000); return True, "submitted via Enter"
    @case("U05", "every button and field shows a visible focus indicator when reached by keyboard")
    def _():
        pg = page(); run_sample(pg); missing = []
        pg.evaluate("()=>document.activeElement&&document.activeElement.blur()")
        for _ in range(16):
            pg.keyboard.press("Tab"); d = pg.evaluate("()=>{const e=document.activeElement,c=getComputedStyle(e);return [e.tagName+'#'+(e.id||e.textContent.slice(0,12)),c.outlineStyle,c.outlineWidth,c.boxShadow]}")
            if d[0].startswith('BODY'): continue
            if d[1] == "none" and d[3] == "none": missing.append(d[0])
        return not missing, missing or "all focusable elements show an outline"
    @case("U06", "server unreachable: clear message and the form works again")
    def _():
        pg = page(); pg.goto(URL); pg.route("**/api/checklist", lambda r: r.abort()); pg.click("#demo"); pg.wait_for_selector("#status.err", timeout=5000); msg = pg.inner_text("#status"); en = pg.is_enabled("#demo") and pg.is_enabled("button.primary")
        return en and "reach" in msg, (msg, en)
    @case("U07", "double-click on 'Try a sample' must not fire two analyses")
    def _():
        pg = page(); pg.goto(URL); n = []; pg.on("request", lambda r: n.append(1) if r.url.endswith("/api/analyze") else None); pg.dblclick("#demo"); pg.wait_for_selector("#out:not([hidden])"); pg.wait_for_timeout(500); return len(n) == 1, f"{len(n)} analyze call(s)"
    @case("U08", "localStorage blocked (private mode): the app still works")
    def _():
        pg = page(); pg.add_init_script("Storage.prototype.setItem=function(){throw new Error('blocked')};Storage.prototype.getItem=function(){throw new Error('blocked')}"); run_sample(pg); return pg.is_visible("#out") and not pg.errs, pg.errs[:1]
    @case("U09", "bad inputs through the UI: javascript: link, 7 links, empty form; each gives a clear message, never a blank screen")
    def _():
        pg = page(); pg.goto(URL); msgs = []
        pg.fill("#q", "visa fee?"); pg.fill("#u", "javascript:alert(1)"); pg.click("button.primary"); pg.wait_for_selector("#out:not([hidden])", timeout=8000); msgs.append(pg.inner_text("#src")[:70])
        pg.fill("#u", "\n".join(f"http://127.0.0.1/{i}" for i in range(7))); pg.click("button.primary"); pg.wait_for_selector("#out:not([hidden])", timeout=8000); n = pg.locator("#src .card").count(); msgs.append(f"{n} source cards")
        pg.reload(); pg.click("button.primary"); pg.wait_for_selector("#status.err"); msgs.append(pg.inner_text("#status"))
        return "Only http" in msgs[0] and n <= 6 and "Enter a question" in msgs[2], msgs
    @case("U10", "print view hides the form and buttons")
    def _():
        pg = page(); run_sample(pg); pg.emulate_media(media="print"); hidden = [s for s in ("#f", "#copy", "#md", "#print") if not pg.is_visible(s)]; return len(hidden) == 4, f"hidden in print: {hidden}"
    @case("U11", "accessibility basics: one h1, main landmark, lang, every control has an accessible name")
    def _():
        pg = page(); run_sample(pg)
        d = pg.evaluate("""()=>({h1:document.querySelectorAll('h1').length,main:!!document.querySelector('main'),lang:document.documentElement.lang,
          unnamed:[...document.querySelectorAll('input,select,textarea,button')].filter(e=>e.type!=='hidden'&&!(e.labels&&e.labels.length)&&!e.textContent.trim()&&!e.getAttribute('aria-label')).map(e=>e.id),
          live:!!document.querySelector('[role=status],[aria-live]')})""")
        return d["h1"] == 1 and d["main"] and d["lang"] == "en" and not d["unnamed"] and d["live"], d
    @case("U12", "6 pasted 190KB sources through the UI: results appear in a reasonable time and page stays responsive")
    def _():
        pg = page(); pg.goto(URL); big = ("The deadline is 30 November 2026. The fee is $350. " + "Lorem ipsum dolor sit amet consectetur. " * 4800)[:190000]
        pg.fill("#q", "scholarship deadline?"); pg.fill("#t", "\n---\n".join(big + str(i) * 40 for i in range(6))); t0 = time.time(); pg.click("button.primary"); pg.wait_for_selector("#out:not([hidden])", timeout=30000); e = time.time() - t0
        return e < 10, f"{e:.1f}s end to end"
    @case("U13", "redesign: gauge/tally/first-open/focus move to the results heading, with zero CSP or console errors (CSSOM style is allowed)")
    def _():
        pg = page(); run_sample(pg); pg.wait_for_timeout(300)
        d = pg.evaluate("""()=>({p:getComputedStyle(document.getElementById('gauge')).getPropertyValue('--p').trim(),tally:[...document.querySelectorAll('#tally li')].map(e=>e.textContent),
          open:document.querySelectorAll('#items details[open]').length,focus:document.activeElement.id,busy:document.getElementById('out').getAttribute('aria-busy'),fav:!!document.querySelector('link[rel=icon]')})""")
        ok = d["p"] == "36" and len(d["tally"]) == 5 and d["open"] == 1 and d["focus"] == "vt" and d["busy"] == "false" and not pg.errs
        return ok, (d, pg.errs[:2])
    @case("U14", "favicon is served (no 404 noise) and example chips fill the question")
    def _():
        pg = page(); pg.goto(URL); st = pg.evaluate("fetch('/favicon.svg').then(r=>r.status+' '+r.headers.get('content-type'))"); pg.click(".chipbtn >> nth=1"); v = pg.input_value("#q")
        return st.startswith("200 image/svg+xml") and "visa" in v, (st, v[:40])
    @case("U15", "copy button gives feedback, expand-all toggles, print opens every finding")
    def _():
        pg = page(); pg.context.grant_permissions(["clipboard-read", "clipboard-write"]); run_sample(pg)
        pg.click("#copy"); pg.wait_for_selector("#copy:has-text('Copied')", timeout=3000); t = pg.inner_text("#copy"); pg.click("#expand"); n = pg.locator("#items details[open]").count(); a = pg.get_attribute("#expand", "aria-expanded")
        pg.click("#expand"); n2 = pg.locator("#items details[open]").count(); pg.evaluate("window.dispatchEvent(new Event('beforeprint'))"); n3 = pg.locator("#items details[open]").count()
        return "Copied" in t and n == 4 and a == "true" and n2 == 0 and n3 == 4, (t, n, a, n2, n3)
    @case("U16", "drag-and-drop: a non-PDF is refused with a message; PDFs fill the input")
    def _():
        pg = page(); pg.goto(URL)
        r = pg.evaluate("""()=>{const dt=new DataTransfer();dt.items.add(new File(['x'],'a.txt',{type:'text/plain'}));document.getElementById('drop').dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}));const m1=document.getElementById('status').textContent;
          const d2=new DataTransfer();d2.items.add(new File(['%PDF-1.4'],'b.pdf',{type:'application/pdf'}));document.getElementById('drop').dispatchEvent(new DragEvent('drop',{dataTransfer:d2,bubbles:true,cancelable:true}));return [m1,document.getElementById('pdf').files.length,document.getElementById('status').textContent]}""")
        return "Only PDF" in r[0] and r[1] == 1 and "1 PDF" in r[2], r
    @case("U17", "before any run: progress steps, results, plan and the expand button are not visible (hidden attribute must win over display rules)")
    def _():
        pg = page(); pg.goto(URL); vis = [x for x in ("#prog", "#out", "#plan", "#expand") if pg.is_visible(x)]; return not vis, vis
    b.close()
srv.terminate()
for r in RES: print(("PASS" if r[1] else "FAIL"), r[0], "|", r[2][:88], "|", "" if r[1] else r[3])
print("FAILED:", [r[0] for r in RES if not r[1]])
