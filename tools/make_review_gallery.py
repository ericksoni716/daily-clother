"""Build the garment review gallery: one page with every drawing the templates can make.

The owner reviews garment shapes often. This writes a single HTML page (for
publishing as a Claude artifact) that shows each signature garment, each value
of each taxonomy axis, the weight ladder, trousers and shoes, with a "looks
right / needs work" choice and a note beside every drawing. Verdicts and notes
are kept in the artifact's own database under `reviews/<card id>`, so they can
be read back and worked through; the drawings themselves are regenerated and
republished each round.

    python tools/make_review_gallery.py OUT.html [--round NAME]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench"))

from closet_bench.illustrate import Fill, Spec, render
from closet_bench.taxonomy import (
    AXES,
    COVERAGE,
    GARMENT_DRAWINGS,
    TOP_AXES,
    surface_extras,
    top_drawing,
)

STYLE = "line"
BLUE, NAVY, TAN, OLIVE, CREAM, SLATE, BROWN = "#a9c3e0", "#27344f", "#c2a878", "#55603f", "#e8e0cf", "#3f4a5f", "#8a5a33"

# What else is on the garment while one axis is varied (the same contexts the tests use).
CONTEXT = {
    "fit": dict(collar="point", placket="front_placket", cuff="barrel_1", hem="curved_shirt_tail"),
    "sleeve_length": dict(neckline="crew", cuff="rib_knit"),
    "neckline": dict(cuff="rib_knit", hem="ribbed_band"),
    "collar": dict(placket="front_placket", cuff="barrel_1", hem="curved_shirt_tail"),
    "placket": dict(collar="point", cuff="barrel_1"),
    "cuff": dict(collar="point", placket="front_placket"),
    "sleeve_construction": dict(neckline="crew", cuff="rib_knit", hem="ribbed_band"),
    "pockets": dict(collar="point", placket="front_placket", cuff="barrel_1"),
    "hem": dict(collar="point", placket="front_placket", cuff="barrel_1"),
}
AXIS_TITLES = {"fit": "Fit", "sleeve_length": "Sleeve length", "neckline": "Neckline", "collar": "Collar and lapels",
               "placket": "Front opening", "cuff": "Cuff", "sleeve_construction": "Sleeve construction",
               "pockets": "Pockets", "hem": "Hem"}


def words(name: str) -> str:
    return name.replace("_", " ")


def top_card(card_id: str, label: str, g: dict, color: str, note: str = "") -> dict:
    p, extras, notes = top_drawing(g)
    svg = render(Spec("top", p, Fill("solid", color), **extras), STYLE, uid=card_id.replace(".", "_"))
    return dict(id=card_id, label=label, svg=svg, note="; ".join([n for n in [note, *notes] if n]))


def other_card(card_id: str, label: str, template: str, params: dict, color: str, **spec) -> dict:
    svg = render(Spec(template, params, Fill("solid", color), **spec), STYLE, uid=card_id.replace(".", "_"))
    return dict(id=card_id, label=label, svg=svg, note="")


def sections() -> list[dict]:
    out = []
    out.append(dict(id="garments", title="Garments", blurb="Each named garment in the taxonomy, drawn from its own axis values.",
                    cards=[top_card(f"garment.{name}", words(name), g, g.get("color", BLUE) if isinstance(g.get("color"), str) else BLUE)
                           for name, g in ((n, {k: v for k, v in g.items()}) for n, g in GARMENT_DRAWINGS.items())]))

    shirt = dict(collar="point", placket="front_placket", cuff="barrel_1", pockets="chest_flap_double", hem="curved_shirt_tail")
    jacket = dict(collar="stand", placket="zip_full", cuff="rib_knit", hem="ribbed_band", fit="relaxed")
    crew = dict(neckline="crew", cuff="rib_knit", hem="ribbed_band")
    ladder = [
        ("weight.shirt_linen", "linen shirt", dict(shirt, fabric="linen", fiber="linen"), BLUE),
        ("weight.shirt_oxford", "oxford shirt", dict(shirt, fabric="oxford", fiber="cotton"), BLUE),
        ("weight.shirt_wool_flannel", "wool flannel overshirt", dict(shirt, fabric="flannel", fiber="woolen_wool"), BLUE),
        ("weight.shirt_fleece", "fleece shirt", dict(shirt, fabric="polar_fleece", fiber="polyester"), BLUE),
        ("weight.bomber_nylon", "thin nylon bomber", dict(jacket, fiber="nylon", fabric="plain", weight="lightweight"), OLIVE),
        ("weight.jacket_melton", "thick wool jacket", dict(jacket, fabric="melton", fiber="woolen_wool"), OLIVE),
        ("weight.crew_merino", "fine merino crew", dict(crew, fabric="flat_knit", fiber="merino", knit_gauge="extra_fine"), SLATE),
        ("weight.crew_shetland", "chunky shetland crew", dict(crew, fabric="flat_knit", fiber="shetland", knit_gauge="chunky"), SLATE),
        ("weight.cable_fine", "fine merino cable", dict(crew, fabric="cable", fiber="merino", knit_gauge="fine"), CREAM),
        ("weight.cable_aran", "chunky aran", dict(crew, fabric="aran", fiber="woolen_wool", knit_gauge="super_chunky"), CREAM),
    ]
    ladder += [(f"weight.cord_{w}", f"corduroy, {words(w)}", dict(shirt, fabric="corduroy", corduroy_wale=w), BROWN)
               for w in ("needlecord", "standard", "wide_wale", "jumbo")]
    ladder += [(f"weight.class_{w}", f"same shirt, {words(w)}", dict(shirt, weight=w), NAVY)
               for w in ("lightweight", "midweight", "heavyweight", "super_heavy")]
    out.append(dict(id="weight", title="Weight and cloth", blurb="The same garments in light and heavy cloth. A stranger should be able to rank each row by thickness.",
                    cards=[top_card(*c) for c in ladder]))

    for axis in TOP_AXES:
        cards = []
        for value in AXES[axis]:
            status, why = COVERAGE[axis][value]
            note = {"drawn": "", "approximate": f"approximate: {why}", "not_drawn": f"not drawn: {why}"}[status]
            cards.append(top_card(f"{axis}.{value}", words(value), {**CONTEXT[axis], axis: value}, BLUE, note))
        out.append(dict(id=axis, title=AXIS_TITLES[axis], blurb=f"Every value of the taxonomy's {words(axis)} axis on an otherwise plain garment.",
                        cards=cards))

    pants = [("jeans_straight", "straight jeans", dict(jeans=True, stitch="contrast"), "#5b7fb5", {}),
             ("jeans_tapered_black", "tapered black jeans", dict(jeans=True, leg="tapered"), "#1d1e22", {}),
             ("chinos", "chinos", dict(leg="straight"), "#c2ab80", {}),
             ("chinos_tapered_ankle", "tapered ankle chinos", dict(leg="tapered", length="ankle"), "#c2ab80", {}),
             ("trousers_pleated_turnup", "wide pleated trousers, turn-ups", dict(leg="wide", pleats=1, hem="turnup"), "#6d7078", {}),
             ("dress_trousers", "creased dress trousers", dict(leg="straight", crease=True), "#2c3140", {}),
             ("cords", "corduroys", dict(leg="straight"), BROWN, surface_extras(dict(fabric="corduroy", corduroy_wale="standard"))),
             ("cargo", "cargo trousers", dict(leg="straight", cargo=True), "#6b6f45", {}),
             ("joggers", "joggers", dict(leg="tapered", waist="drawstring", hem="rib"), "#8f9296", {}),
             ("shorts", "chino shorts", dict(length="short"), "#6d7a4e", {}),
             ("shorts_jeans", "denim shorts", dict(length="short", jeans=True), "#7f9bc9", {}),
             ("shorts_elastic", "drawstring shorts", dict(length="short", waist="drawstring"), NAVY, {})]
    out.append(dict(id="trousers", title="Trousers and shorts", blurb="Cuts, waists, pockets and hems.",
                    cards=[other_card(f"pants.{i}", label, "pants", p, col, **extra) for i, label, p, col, extra in pants]))

    shoes = [("low_sneaker", "low sneaker", dict(style="low_sneaker"), "#f2f2f0", {}),
             ("low_sneaker_stripe", "low sneaker, side stripe and heel tab", dict(style="low_sneaker", stripe="side", heel_tab="contrast"), "#f2f2f0", dict(trim_color=NAVY)),
             ("high_top", "canvas high-top", dict(style="high_top", height="high"), "#1f2024", dict(lace_color="#f4f1ea")),
             ("runner", "runner", dict(style="runner"), "#3f6fb0", dict(trim_color="#e3c341", lace_color="#f4f1ea")),
             ("chunky", "chunky-sole sneaker", dict(style="low_sneaker", sole="chunky"), "#9fa3a8", {}),
             ("slip_on", "canvas slip-on", dict(style="slip_on"), "#6e2633", {}),
             ("loafer", "penny loafer", dict(style="loafer"), "#5a3a26", {}),
             ("derby", "derby", dict(style="derby"), "#1d1e22", {}),
             ("oxford", "cap-toe oxford", dict(style="oxford", toe_cap="stitched"), "#7a4a2a", {}),
             ("boot", "lace-up boot", dict(style="boot", height="high"), "#8a5a33", {}),
             ("chelsea_boot", "chelsea boot", dict(style="chelsea_boot", height="high"), "#3a2a20", {})]
    out.append(dict(id="shoes", title="Shoes", blurb="The nine shoe shapes and their details. There is no sandal shape yet.",
                    cards=[other_card(f"shoe.{i}", label, "sneaker", p, col, **extra) for i, label, p, col, extra in shoes]))
    return out


PAGE = r"""<title>Garment Review</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600&display=swap">
<style>
/* Layout: a cutting-room pin board. A sticky tally bar, then one section per part of the garment, each a grid of drawing cards with the verdict controls directly under the drawing. */
:root {
  --bg: #eef0f3; --surface: #ffffff; --ink: #1a2230; --muted: #5d6676; --line: #d5dae2;
  --accent: #2f4f8f; --accent-ink: #ffffff; --good: #2c7a55; --good-bg: #e3f2ea; --warn: #a8501a; --warn-bg: #fbeadb;
  --paper: #f1eee8;
  --display: "Space Grotesk", "Segoe UI", system-ui, sans-serif; --body: "Inter", "Segoe UI", system-ui, sans-serif;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #141922; --surface: #1d2430; --ink: #e8ecf3; --muted: #9aa5b8; --line: #323c4d;
  --accent: #8fb0f0; --accent-ink: #10151d; --good: #6fcf9f; --good-bg: #1d3a2d; --warn: #f0a268; --warn-bg: #40291a;
  --paper: #f1eee8; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #141922; --surface: #1d2430; --ink: #e8ecf3; --muted: #9aa5b8; --line: #323c4d;
  --accent: #8fb0f0; --accent-ink: #10151d; --good: #6fcf9f; --good-bg: #1d3a2d; --warn: #f0a268; --warn-bg: #40291a;
  --paper: #f1eee8; color-scheme: dark }
body { background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 15px; line-height: 1.5; }
body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); z-index: 10; background: var(--bg); }
.wrap { max-width: 1500px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 20px 60px; display: flex; flex-direction: column; gap: 28px; }
header h1 { font-family: var(--display); font-size: 28px; font-weight: 600; margin: 0 0 6px; text-wrap: balance; }
header p { margin: 0; color: var(--muted); max-width: 68ch; }
.bar { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 5; background: var(--bg); padding-block: 10px; border-bottom: 1px solid var(--line); display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; }
.tally { display: flex; gap: 14px; font-variant-numeric: tabular-nums; font-size: 14px; color: var(--muted); }
.tally b { color: var(--ink); font-weight: 600; }
.chips, .nav { display: flex; flex-wrap: wrap; gap: 6px; }
.chip, .nav a { border: 1px solid var(--line); background: var(--surface); color: var(--ink); border-radius: 999px; padding: 5px 12px; font: 500 13px var(--body); cursor: pointer; text-decoration: none; }
.chip[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
.chip:focus-visible, .nav a:focus-visible, .verdict button:focus-visible, textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.status { font-size: 13px; color: var(--muted); margin-left: auto; }
.status.bad { color: var(--warn); }
section { display: flex; flex-direction: column; gap: 12px; scroll-margin-top: 110px; }
section h2 { font-family: var(--display); font-size: 20px; font-weight: 600; margin: 0; }
section .blurb { margin: 0; color: var(--muted); font-size: 14px; max-width: 68ch; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 14px; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }
.card[data-verdict="ok"] { border-color: var(--good); }
.card[data-verdict="fix"] { border-color: var(--warn); }
.card .art { background: var(--paper); }
.card .art svg { display: block; width: 100%; height: auto; }
.card .body { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 8px; }
.card h3 { font: 600 14px var(--body); margin: 0; overflow-wrap: anywhere; }
.card .approx { font-size: 12px; color: var(--muted); margin: 0; overflow-wrap: anywhere; }
.verdict { display: flex; gap: 6px; }
.verdict button { flex: 1; border: 1px solid var(--line); background: var(--surface); color: var(--ink); border-radius: 7px; padding: 6px 4px; font: 500 13px var(--body); cursor: pointer; }
.verdict button[aria-pressed="true"].ok { background: var(--good-bg); border-color: var(--good); color: var(--good); }
.verdict button[aria-pressed="true"].fix { background: var(--warn-bg); border-color: var(--warn); color: var(--warn); }
.verdict button:disabled, textarea:disabled { opacity: .55; cursor: not-allowed; }
textarea { width: 100%; box-sizing: border-box; min-height: 54px; resize: vertical; border: 1px solid var(--line); border-radius: 7px; background: var(--bg); color: var(--ink); font: 400 13px/1.4 var(--body); padding: 6px 8px; }
.meta { font-size: 12px; color: var(--muted); min-height: 16px; margin: 0; }
.meta.stale { color: var(--warn); }
.empty { color: var(--muted); font-size: 14px; margin: 0; }
@media (prefers-reduced-motion: no-preference) { .card { transition: border-color .15s; } }
</style>
<div class="wrap">
  <header>
    <h1>Garment Review</h1>
    <p>Every drawing the templates can make, as of round <b id="round"></b>. Mark each one and say what is wrong; your marks are saved as you go and read back when the drawings are reworked.</p>
  </header>
  <div class="bar">
    <div class="tally"><span><b id="n-fix">0</b> need work</span><span><b id="n-ok">0</b> look right</span><span><b id="n-none">0</b> not reviewed</span></div>
    <div class="chips" role="group" aria-label="Show">
      <button class="chip" id="f-all" aria-pressed="true">All</button>
      <button class="chip" id="f-fix" aria-pressed="false">Needs work</button>
      <button class="chip" id="f-none" aria-pressed="false">Not reviewed</button>
    </div>
    <nav class="nav" id="nav" aria-label="Sections"></nav>
    <span class="status" id="status">Loading saved reviews…</span>
  </div>
  <main id="main"></main>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  var DATA = JSON.parse(document.getElementById('data').textContent);
  var ROUND = DATA.round, reviews = {}, db = null, canSave = false, filter = 'all', pending = {}, timers = {};
  var main = document.getElementById('main'), nav = document.getElementById('nav'), statusEl = document.getElementById('status');
  document.getElementById('round').textContent = ROUND;

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function setStatus(text, bad) { statusEl.textContent = text; statusEl.className = 'status' + (bad ? ' bad' : ''); }

  var cards = {};
  DATA.sections.forEach(function (s) {
    var sec = el('section'); sec.id = s.id;
    sec.appendChild(el('h2', null, s.title));
    sec.appendChild(el('p', 'blurb', s.blurb));
    var grid = el('div', 'grid'); sec.appendChild(grid);
    var empty = el('p', 'empty', 'Nothing here matches the filter.'); empty.hidden = true; sec.appendChild(empty);
    s.cards.forEach(function (c) {
      var card = el('article', 'card'); card.dataset.id = c.id;
      var art = el('div', 'art'); art.innerHTML = c.svg; card.appendChild(art);
      var body = el('div', 'body');
      body.appendChild(el('h3', null, c.label));
      if (c.note) body.appendChild(el('p', 'approx', c.note));
      var v = el('div', 'verdict'); v.setAttribute('role', 'group'); v.setAttribute('aria-label', 'Verdict for ' + c.label);
      var ok = el('button', 'ok', 'Looks right'), fix = el('button', 'fix', 'Needs work');
      ok.type = fix.type = 'button'; ok.id = 'ok-' + c.id; fix.id = 'fix-' + c.id;
      ok.setAttribute('aria-pressed', 'false'); fix.setAttribute('aria-pressed', 'false');
      v.appendChild(ok); v.appendChild(fix); body.appendChild(v);
      var ta = el('textarea'); ta.id = 'note-' + c.id; ta.placeholder = 'What is wrong, or what would make it right'; ta.setAttribute('aria-label', 'Note for ' + c.label);
      body.appendChild(ta);
      var meta = el('p', 'meta'); body.appendChild(meta);
      card.appendChild(body); grid.appendChild(card);
      cards[c.id] = { card: card, ok: ok, fix: fix, ta: ta, meta: meta, section: sec };
      ok.addEventListener('click', function () { choose(c.id, 'ok'); });
      fix.addEventListener('click', function () { choose(c.id, 'fix'); });
      ta.addEventListener('input', function () { clearTimeout(timers[c.id]); timers[c.id] = setTimeout(function () { saveNote(c.id); }, 1200); });
      ta.addEventListener('change', function () { clearTimeout(timers[c.id]); saveNote(c.id); });
    });
    main.appendChild(sec);
    var a = el('a', null, s.title); a.href = '#' + s.id; nav.appendChild(a);
  });

  function paint(id) {
    var c = cards[id], r = reviews[id] || {};
    var verdict = r.verdict || '';
    c.card.dataset.verdict = verdict;
    c.ok.setAttribute('aria-pressed', String(verdict === 'ok'));
    c.fix.setAttribute('aria-pressed', String(verdict === 'fix'));
    if (document.activeElement !== c.ta && !timers[id + ':dirty']) c.ta.value = r.note || '';
    c.ok.disabled = c.fix.disabled = c.ta.disabled = !canSave;
    if ((r.verdict || r.note) && r.round && r.round !== ROUND) { c.meta.textContent = 'Marked on an earlier drawing (round ' + r.round + '). Check it again.'; c.meta.className = 'meta stale'; }
    else { c.meta.textContent = pending[id] ? 'Saving…' : ((r.verdict || r.note) ? 'Saved' : ''); c.meta.className = 'meta'; }
  }
  function paintAll() {
    var n = { ok: 0, fix: 0, none: 0 };
    Object.keys(cards).forEach(function (id) {
      paint(id);
      var r = reviews[id] || {}, stale = r.round && r.round !== ROUND;
      var state = (r.verdict === 'fix') ? 'fix' : (r.verdict === 'ok' && !stale) ? 'ok' : 'none';
      n[state]++;
      cards[id].card.hidden = !(filter === 'all' || filter === state);
    });
    document.getElementById('n-ok').textContent = n.ok;
    document.getElementById('n-fix').textContent = n.fix;
    document.getElementById('n-none').textContent = n.none;
    DATA.sections.forEach(function (s) {
      var sec = document.getElementById(s.id), any = s.cards.some(function (c) { return !cards[c.id].card.hidden; });
      sec.querySelector('.empty').hidden = any;
    });
  }
  ['all', 'fix', 'none'].forEach(function (f) {
    document.getElementById('f-' + f).addEventListener('click', function () {
      filter = f;
      ['all', 'fix', 'none'].forEach(function (g) { document.getElementById('f-' + g).setAttribute('aria-pressed', String(g === f)); });
      paintAll();
    });
  });

  // one write at a time per drawing; the newest state always wins
  function save(id) {
    if (!db || !canSave) return;
    if (pending[id]) { pending[id] = 'again'; return; }
    pending[id] = 'now'; paint(id);
    var r = reviews[id] || {};
    var body = { verdict: r.verdict || '', note: r.note || '', round: ROUND, at: new Date().toISOString() };
    db.doc('reviews/' + id).set(body).then(function () {
      var again = pending[id] === 'again'; delete pending[id];
      if (again) save(id); else paint(id);
    }, function (e) {
      delete pending[id];
      if (e && e.code === 'invalid_argument') { canSave = false; setStatus('You can look, but this view cannot save reviews.', true); paintAll(); }
      else { cards[id].meta.textContent = 'Not saved. Change it again to retry.'; cards[id].meta.className = 'meta stale'; }
    });
  }
  function choose(id, verdict) {
    var r = Object.assign({}, reviews[id] || {});
    r.verdict = (r.verdict === verdict && (!r.round || r.round === ROUND)) ? '' : verdict;
    r.note = cards[id].ta.value; r.round = ROUND;
    reviews[id] = r; paintAll(); save(id);
  }
  function saveNote(id) {
    var r = Object.assign({}, reviews[id] || {});
    if ((r.note || '') === cards[id].ta.value) return;
    r.note = cards[id].ta.value; r.round = ROUND;
    if (r.note && !r.verdict) r.verdict = 'fix';   // a note with no verdict means something is wrong
    reviews[id] = r; paintAll(); save(id);
  }

  paintAll();
  var use = window.claude && window.claude.use ? window.claude.use('db') : Promise.resolve(null);
  use.then(function (store) {
    if (!store) { setStatus('Reviews cannot be saved in this view. Open the page in Claude while signed in.', true); return; }
    db = store; canSave = true;
    var slow = setTimeout(function () { setStatus('Saved reviews cannot be reached yet; what you see may be out of date.', true); }, 10000);
    db.collection('reviews').limit(1000).onSnapshot(function (snap) {
      var next = {};
      snap.docs.forEach(function (d) { if (cards[d.id]) next[d.id] = Object.assign({}, d.data()); });
      Object.keys(pending).forEach(function (id) { if (reviews[id]) next[id] = reviews[id]; });   // keep what is being saved
      reviews = next;
      if (!snap.metadata.fromCache) { clearTimeout(slow); setStatus('Reviews are saved as you go.'); }
      paintAll();
    }, function () { clearTimeout(slow); canSave = false; setStatus('Saved reviews could not be loaded.', true); paintAll(); });
  }, function () { setStatus('Reviews cannot be saved in this view.', true); });
})();
</script>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--round", default=time.strftime("%Y-%m-%d.%H%M", time.gmtime()))
    a = ap.parse_args()
    data = dict(round=a.round, sections=sections())
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    a.out.write_text(PAGE.replace("__DATA__", payload), encoding="utf-8")
    n = sum(len(s["cards"]) for s in data["sections"])
    print(f"{a.out}: {n} drawings in {len(data['sections'])} sections, round {a.round}, {a.out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
