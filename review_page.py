"""Builds an HTML page to check and correct the answers of CLIP, 50 photos per page.

Usage:
    python review_page.py PHOTO_FOLDER [--results results_2/results.csv]
                          [--expected expected_2.json] [--output results_2/review.html]

The page keeps the progress in the browser and exports an expected answers file
(same format as expected.json) readable by test_clip.py --expected.
Hidden criteria ("hidden": true) are not shown; their known answers are kept in the export.
Every list has a "+ New value…" entry: the values typed there are offered on every photo and exported
like the others. A criterion with "values_if" offers other values depending on an earlier answer, and
"manual_values" are offered on the page only: CLIP does not assess them.
Photos answered "yes" for "blurry" or with a person ("front", "back") stand out with another background.
Each card shows the shooting date and the camera settings read in the EXIF of the photo, and its
image gets a text alternative built from the answers.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from analyzer import NOT_APPLICABLE, UNDETERMINED, possible_values
from labels import SWITCH_CSS, SWITCH_HTML, load_labels, switch_js
from photo_exif import exif_for_page, read_exif


def read_predictions(csv_path, names):
    photos = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            predicted = {name: row[name] or NOT_APPLICABLE for name in names}
            scores = {name: float(row[f"{name}_score"]) if row[f"{name}_score"] else None for name in names}
            photos.append({"file": row["file"], "predicted": predicted, "scores": scores})
    return photos


PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CLIP review</title>
<style>
  :root { --to-review: "to review"; }
  body { font-family: system-ui, sans-serif; margin: 0; background: #f4f4f4; color: #222; }
  header { position: sticky; top: 0; z-index: 5; background: #fff; box-shadow: 0 1px 4px #0002;
           padding: 8px 16px; display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
  header .stats { font-size: 14px; color: #555; }
  header .actions { margin-left: auto; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  button, select { font: inherit; }
  button { padding: 5px 12px; cursor: pointer; }
  button.main { background: #2a7d2a; color: #fff; border: 0; border-radius: 4px; }
  main { padding: 16px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
  .card { background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px #0002;
          border: 3px solid transparent; }
  .card.checked { border-color: #2a7d2a55; }
  .card.blurry { background: #e9ddff; }
  .card.blurry table td { border-top-color: #d6c6f5; }
  .card.person { background: #ffdcdc; }
  .card.person table td { border-top-color: #f5c6c6; }
  .card img { width: 100%; height: 200px; object-fit: cover; display: block; cursor: zoom-in; background: #ddd; }
  .name { padding: 6px 10px; font-weight: 600; font-size: 13px; word-break: break-all;
          display: flex; justify-content: space-between; gap: 6px; }
  .name .state { font-weight: normal; color: #2a7d2a; white-space: nowrap; }
  .alt { padding: 6px 10px 0; font-weight: 600; font-size: 13px; }
  .alt + .name { padding-top: 2px; font-weight: normal; }
  .exif { padding: 0 10px 6px; font-size: 12px; color: #555; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  td { padding: 2px 10px; border-top: 1px solid #eee; }
  td:first-child { color: #555; width: 45%; }
  td select { width: 100%; }
  tr.changed select { background: #ffe2b8; font-weight: 600; }
  tr.changed td:first-child::after { content: " ✎"; color: #c06000; }
  tr.to-review select { background: #fff3a0; }
  tr.to-review td:first-child::after { content: " " var(--to-review); color: #9a7b00; font-size: 11px; }
  label.filter { font-size: 14px; }
  label.filter select { padding: 3px 6px; }
  .score { color: #999; font-size: 11px; }
  nav { display: flex; gap: 8px; align-items: center; justify-content: center; margin: 20px 0; flex-wrap: wrap; }
  #viewer { position: fixed; inset: 0; z-index: 10; background: #000e; display: none;
            flex-direction: column; align-items: center; justify-content: center; gap: 10px; }
  #viewer.open { display: flex; }
  #viewer img { max-width: 96vw; max-height: 86vh; object-fit: contain; }
  #viewer button { font-size: 16px; padding: 8px 20px; }
  #viewer .caption { color: #ddd; font-size: 14px; }
__SWITCH_CSS__
</style></head><body>
<header>
  <strong data-t="ui:review_title">CLIP review</strong>
  <span class="stats" id="stats"></span>
  <label class="filter"><span data-t="ui:show"></span>
    <select id="mode">
      <option value="all" data-t="ui:mode_all"></option>
      <option value="to_review" data-t="ui:filter"></option>
      <option value="disagree" data-t="ui:mode_disagree"></option>
    </select>
  </label>
  <span class="actions">
    <button id="export" data-t="ui:export" data-vars='{"file": "__EXPORT_NAME__"}'></button>
    <button id="import" data-t="ui:import"></button>
    <input type="file" id="import-file" accept=".json" hidden>
    __SWITCH_HTML__
  </span>
</header>
<main>
  <nav class="pagination"></nav>
  <div class="grid" id="grid"></div>
  <nav class="pagination"></nav>
  <nav><button class="main" id="validate" data-t="ui:validate"></button></nav>
</main>
<div id="viewer"><button id="back" data-t="ui:back"></button><img alt=""><div class="caption"></div></div>
<script>
__SWITCH_JS__
const DATA = __DATA__;
const PER_PAGE = 50, NA = "—", UNDETERMINED = "undetermined", NEW_VALUE = "\\u0000new";
// The version changes with the criteria: progress saved for older criteria is ignored.
const KEY = "clip-review:" + DATA.folder + ":" + DATA.version;
const NAMES = DATA.criteria.map(([name]) => name);

// state.corrections[file][criterion] = chosen value; state.checked[file] = true
// state.mode: "all", "to_review" or "disagree" (see computeList)
// state.added[criterion] = values typed with "+ New value…"
let state = { corrections: {}, checked: {}, page: 0, mode: null, added: {} };
try { Object.assign(state, JSON.parse(localStorage.getItem(KEY)) || {}); } catch (e) {}
state.added = state.added || {};
// Known expected answers are the starting point; a photo is checked only if all its shown criteria are known.
for (const [f, vals] of Object.entries(DATA.expected)) {
  if (state.corrections[f]) continue;
  state.corrections[f] = {};
  for (const [k, v] of Object.entries(vals)) if (NAMES.includes(k)) state.corrections[f][k] = v === null ? NA : v;
  if (NAMES.every(n => n in vals)) state.checked[f] = true;
}
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }

// Values that are not in criteria.json: found in the expected answers file or typed in this page.
const conditionalValues = name => Object.values(DATA.valuesIf[name] || {}).flatMap(by => Object.values(by).flat());
const known = Object.fromEntries(DATA.criteria.map(([name, options]) => [name, new Set([...options, ...conditionalValues(name)])]));
const extras = Object.fromEntries(NAMES.map(name => [name, new Set()]));
function addExtra(name, v) { if (v !== null && v !== undefined && v !== NA && !known[name].has(v)) extras[name].add(v); }
function addValue(name, v) { addExtra(name, v); state.added[name] = [...extras[name]]; }
for (const [name, values] of Object.entries(DATA.manual)) for (const v of values) addExtra(name, v);
for (const vals of Object.values(DATA.expected)) for (const name of NAMES) addExtra(name, vals[name]);
for (const [name, values] of Object.entries(state.added)) if (name in extras) for (const v of values) addExtra(name, v);

// Values of a criterion for a photo: those of criteria.json ("values_if" replaces them depending on the
// answers of the photo), the extra values, and the current answer so that it is never lost. A "sorted"
// criterion has its values sorted by their label in the chosen language, the others keep their order;
// "undetermined" and "—" stay last.
function optionsOf(criterion, options, p) {
  const special = Object.entries(DATA.valuesIf[criterion] || {}).flatMap(([name, by]) => by[answer(p, name)] || []);
  const values = new Set([...(special.length ? special : options.filter(o => o !== NA)), ...extras[criterion]]);
  if (value(p, criterion) !== NA) values.add(value(p, criterion));
  if (!DATA.sorted.includes(criterion)) return [...values, NA];
  const collator = new Intl.Collator(lang);
  const label = v => t("v:" + criterion + ":" + v);
  return [...[...values].sort((a, b) => (a === UNDETERMINED) - (b === UNDETERMINED)
    || collator.compare(label(a), label(b))), NA];
}

const photos = DATA.photos;
const value = (p, name) => (state.corrections[p.file] || {})[name] ?? p.predicted[name];
// "except" / "only_if" of criteria.json, applied to the current answers of the photo (as in the app):
// a criterion hidden this way is not shown and its answer is "—".
function shown(p, name) {
  const { except = {}, only_if = {} } = DATA.conditions[name] || {};
  if (Object.entries(except).some(([n, values]) => values.includes(answer(p, n)))) return false;
  return Object.entries(only_if).every(([n, values]) => values.includes(answer(p, n)));
}
const answer = (p, name) => shown(p, name) ? value(p, name) : NA;
// Criterion to review: photo not validated yet and no value given by the user for this criterion.
const toReview = (p, name) => !state.checked[p.file] && !(name in (state.corrections[p.file] || {}));
const unchecked = p => !state.checked[p.file];
// Disagreement between the expected answers file given to the page and CLIP. It does not follow
// the corrections made in the page, so that a photo corrected here stays in the list.
const disagrees = p => p.file in DATA.expected && NAMES.some(name => name in DATA.expected[p.file]
  && (DATA.expected[p.file][name] ?? NA) !== p.predicted[name]);
// Progress saved by an older page: "filter" (true/false) became "mode".
if ("filter" in state) { state.mode = state.filter ? "to_review" : "all"; delete state.filter; }
// Some photos already checked, others not: start with those left to check.
if (state.mode === null) state.mode = photos.some(p => state.checked[p.file]) && photos.some(unchecked) ? "to_review" : "all";
// "to_review": the photos not validated yet; "disagree": see disagrees().
let list = [];
function computeList() {
  if (state.mode === "to_review") list = photos.filter(unchecked);
  else if (state.mode === "disagree") list = photos.filter(disagrees);
  else list = photos;
}
const nbPages = () => Math.max(1, Math.ceil(list.length / PER_PAGE));

function showStats() {
  const nbChecked = photos.filter(p => state.checked[p.file]).length;
  let nbChanges = 0;
  for (const p of photos) for (const name of NAMES) if (answer(p, name) !== p.predicted[name]) nbChanges++;
  const left = photos.filter(unchecked).length;
  document.getElementById("stats").textContent = t("ui:stats", {
    page: state.page + 1, pages: nbPages(), checked: nbChecked, total: photos.length, left, changes: nbChanges,
    disagree: photos.filter(disagrees).length });
}

function showPagination() {
  for (const nav of document.querySelectorAll(".pagination")) {
    nav.innerHTML = "";
    for (let i = 0; i < nbPages(); i++) {
      const b = document.createElement("button");
      const slice = list.slice(i * PER_PAGE, (i + 1) * PER_PAGE);
      const done = slice.every(p => state.checked[p.file]);
      b.textContent = (i + 1) + (done ? " ✓" : "");
      b.disabled = i === state.page;
      b.onclick = () => goTo(i);
      nav.appendChild(b);
    }
  }
}

function card(p) {
  const div = document.createElement("div");
  div.className = "card" + (state.checked[p.file] ? " checked" : "");
  const markCard = () => {
    div.classList.toggle("blurry", value(p, "blurry") === "yes");
    div.classList.toggle("person", ["front", "back"].includes(answer(p, "person")));
  };
  markCard();
  const img = document.createElement("img");
  img.loading = "lazy"; img.src = DATA.base + encodeURIComponent(p.file).replace(/%2F/g, "/");
  img.alt = altText(p);
  img.onclick = () => openViewer(img.src, p.file, img.alt);
  div.appendChild(img);
  const alt = document.createElement("div");
  alt.className = "alt";
  alt.textContent = img.alt;
  div.appendChild(alt);
  const name = document.createElement("div");
  name.className = "name";
  name.innerHTML = `<span></span><span class="state">${state.checked[p.file] ? t("ui:checked") : ""}</span>`;
  name.firstChild.textContent = p.file;
  div.appendChild(name);
  if (exifText(p.exif)) {
    const exif = document.createElement("div");
    exif.className = "exif";
    exif.textContent = exifText(p.exif);
    div.appendChild(exif);
  }
  const table = document.createElement("table");
  const date = table.insertRow();
  date.insertCell().textContent = t("ui:date");
  date.insertCell().textContent = takenText(p.exif);
  const marks = [];
  for (const [criterion, options] of DATA.criteria) {
    const tr = document.createElement("tr");
    const td1 = document.createElement("td"), td2 = document.createElement("td");
    const sc = p.scores[criterion];
    td1.textContent = t("c:" + criterion) + " ";
    const score = document.createElement("span");
    score.className = "score";
    score.textContent = sc === null ? "" : Math.round(sc * 100) + " %";
    td1.appendChild(score);
    const sel = document.createElement("select");
    const fill = () => {
      sel.replaceChildren();
      for (const o of optionsOf(criterion, options, p)) {
        const opt = document.createElement("option");
        opt.value = o;
        // No score: the value does not come from CLIP.
        opt.textContent = (o === NA ? NA : t("v:" + criterion + ":" + o)) + (o === p.predicted[criterion] && sc !== null ? "  (CLIP)" : "");
        sel.appendChild(opt);
      }
      const opt = document.createElement("option");
      opt.value = NEW_VALUE;
      opt.textContent = t("ui:new_value");
      sel.appendChild(opt);
      sel.value = value(p, criterion);
    };
    fill();
    // A criterion that becomes visible with no answer ("—", e.g. hidden by CLIP's own answers)
    // is to review too; a free criterion may stay empty.
    const mark = () => {
      if (criterion in DATA.valuesIf) fill();
      tr.hidden = !shown(p, criterion);
      tr.classList.toggle("changed", sel.value !== p.predicted[criterion]);
      tr.classList.toggle("to-review", toReview(p, criterion) || (sel.value === NA && !DATA.free.includes(criterion)));
    };
    marks.push(mark);
    sel.onchange = () => {
      let chosen = sel.value;
      if (chosen === NEW_VALUE) {
        chosen = (prompt(t("ui:new_value_prompt", { criterion: t("c:" + criterion) })) || "").trim();
        if (!chosen || chosen === NA) { sel.value = value(p, criterion); return; }
        addValue(criterion, chosen);
      }
      state.corrections[p.file] = state.corrections[p.file] || {};
      state.corrections[p.file][criterion] = chosen;
      save();
      // A new value is offered on every card of the page: they are redrawn.
      if (sel.value === NEW_VALUE) { goTo(state.page, false); return; }
      // An answer can show or hide the following criteria (e.g. vehicle -> vehicle type).
      for (const m of marks) m();
      markCard(); img.alt = alt.textContent = altText(p); showStats();
    };
    td2.appendChild(sel); tr.append(td1, td2); table.appendChild(tr);
  }
  for (const m of marks) m();
  div.appendChild(table);
  return div;
}

// "11 septembre 2024" in the chosen language, without the time; only an EXIF date is shown.
function takenText(exif) {
  if (!exif.taken) return t("ui:unknown_date");
  // Read and shown as UTC: the camera's local time stays as it was written.
  return new Intl.DateTimeFormat(lang, { dateStyle: "long", timeZone: "UTC" })
    .format(new Date(exif.taken + "Z"));
}

// "SONY ILCA-68 · 1/500 s · f/8 · 20 mm · ISO 100", with only what the EXIF gives; "No EXIF" without any.
function exifText(exif) {
  const number = n => n.toLocaleString(lang, { maximumFractionDigits: 1 });
  const s = exif.exposure_time;
  const settings = [
    exif.camera,
    s && (s < 1 ? `1/${Math.round(1 / s)} s` : `${number(s)} s`),
    exif.f_number && `f/${number(exif.f_number)}`,
    exif.focal_length && `${number(exif.focal_length)} mm`,
    exif.iso && `ISO ${Math.round(exif.iso)}`,
  ].filter(Boolean);
  return settings.length || exif.taken ? settings.join(" · ") : t("ui:no_exif");
}

// Text alternative built from the answers, e.g. "Image d'un château en ruine sous le soleil".
// A French adjective agrees with the gender of the subject (labels.json, "alt").
function altText(p) {
  const pick = name => (LABELS.alt[name] || {})[answer(p, name)];
  const subject = pick("vehicle_type") || pick("place_type") || LABELS.alt.place_type.undetermined;
  const phrase = name => {
    const entry = pick(name);
    if (!entry) return "";
    return lang === "en" || typeof entry.fr === "string" ? entry[lang] : entry.fr[subject.gender || "m"] || "";
  };
  const words = ["condition", "weather", "time_of_day"].map(phrase).filter(Boolean);
  return [t("ui:photo_alt", { subject: subject[lang] }), ...words].join(" ");
}

function goTo(i, scroll = true) {
  computeList();
  state.page = Math.max(0, Math.min(nbPages() - 1, i)); save();
  const grid = document.getElementById("grid");
  grid.innerHTML = "";
  for (const p of list.slice(state.page * PER_PAGE, (state.page + 1) * PER_PAGE)) grid.appendChild(card(p));
  if (!list.length) grid.textContent = t("ui:nothing_left");
  showPagination(); showStats();
  if (scroll) window.scrollTo(0, 0);
}

const mode = document.getElementById("mode");
mode.value = state.mode;
mode.onchange = () => { state.mode = mode.value; goTo(0); };

document.getElementById("validate").onclick = () => {
  const page = list.slice(state.page * PER_PAGE, (state.page + 1) * PER_PAGE);
  for (const p of page) state.checked[p.file] = true;
  save();
  // In "to_review" mode, validated photos leave the list: the next page takes their place.
  const shrinks = state.mode === "to_review";
  const next = shrinks ? state.page : state.page + 1;
  const last = shrinks ? list.length <= page.length : state.page >= nbPages() - 1;
  goTo(next);
  if (last) alert(t("ui:last_page"));
};

// Export: all the values of the checked photos (confirmed or corrected); "—" becomes null, as does
// a criterion hidden by the answers. Known answers of hidden criteria ("hidden": true) are kept.
// A photo of the expected answers file not validated again here (e.g. one that lost a criterion
// when the criteria changed) is exported as it was in that file, so that the export loses nothing.
document.getElementById("export").onclick = () => {
  const output = {};
  for (const p of photos) {
    if (!state.checked[p.file]) {
      if (p.file in DATA.expected) output[p.file] = DATA.expected[p.file];
      continue;
    }
    output[p.file] = { ...(DATA.expected[p.file] || {}) };
    for (const name of NAMES) {
      const v = answer(p, name);
      output[p.file][name] = v === NA ? null : v;
    }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(output, null, 2)], { type: "application/json" }));
  a.download = DATA.exportName;
  a.click();
  URL.revokeObjectURL(a.href);
};

// Import: takes back an exported file. As when the page opens, a photo is checked only if all its
// shown criteria are known: the others (exported as they were) stay to review.
document.getElementById("import").onclick = () => document.getElementById("import-file").click();
document.getElementById("import-file").onchange = async e => {
  const f = e.target.files[0];
  if (!f) return;
  try {
    const data = JSON.parse(await f.text());
    for (const [file, vals] of Object.entries(data)) {
      state.corrections[file] = {};
      for (const [k, v] of Object.entries(vals)) if (NAMES.includes(k)) state.corrections[file][k] = v === null ? NA : v;
      if (NAMES.every(n => n in vals)) state.checked[file] = true;
      else delete state.checked[file];
      // Values typed in another copy of the page: offered here too.
      for (const k of NAMES) addValue(k, vals[k]);
    }
    save(); goTo(state.page);
  } catch (err) { alert(t("ui:unreadable", { error: err.message })); }
  e.target.value = "";
};

const viewer = document.getElementById("viewer"), large = viewer.querySelector("img");
function openViewer(src, name, alt) { large.src = src; large.alt = alt; viewer.querySelector(".caption").textContent = name; viewer.classList.add("open"); }
function closeViewer() { viewer.classList.remove("open"); large.removeAttribute("src"); }
document.getElementById("back").onclick = closeViewer;
viewer.onclick = e => { if (e.target === viewer) closeViewer(); };
document.addEventListener("keydown", e => { if (e.key === "Escape") closeViewer(); });

function translatePage() {
  document.documentElement.style.setProperty("--to-review", JSON.stringify(t("ui:to_review")));
  goTo(state.page, false);
}
onLanguageChange = translatePage;
translate(); translatePage();
</script>
</body></html>
"""


def main():
    parser = argparse.ArgumentParser(description="Review page for the answers of CLIP.")
    parser.add_argument("folder", type=Path, help="folder of the analysed photos")
    parser.add_argument("--results", type=Path, default=Path("results_2/results.csv"))
    parser.add_argument("--criteria", type=Path, default=Path(__file__).with_name("criteria.json"))
    parser.add_argument("--expected", type=Path, default=Path(__file__).with_name("expected_2.json"))
    parser.add_argument("--output", type=Path, default=Path("results_2/review.html"))
    args = parser.parse_args()

    with open(args.criteria, encoding="utf-8") as f:
        criteria = json.load(f)
    expected = {}
    if args.expected.exists():
        with open(args.expected, encoding="utf-8") as f:
            expected = json.load(f)

    page_criteria = possible_values(criteria)
    photos = read_predictions(args.results, [name for name, _ in page_criteria])
    for photo in photos:
        photo["exif"] = exif_for_page(read_exif(args.folder / photo["file"]))
    data = {
        "folder": str(args.folder.resolve()),
        "version": hashlib.sha1(json.dumps(page_criteria).encode()).hexdigest()[:10],
        "base": args.folder.resolve().as_uri() + "/",
        "exportName": args.expected.name,
        "criteria": page_criteria,
        "free": [c["name"] for c in criteria.get("choices", []) if c.get("free")],
        "sorted": [c["name"] for c in criteria.get("choices", []) if c.get("sorted")],
        "valuesIf": {c["name"]: c["values_if"] for c in criteria.get("choices", []) if "values_if" in c},
        "manual": {c["name"]: c["manual_values"] for c in criteria.get("choices", []) if "manual_values" in c},
        "conditions": {c["name"]: {k: c[k] for k in ("except", "only_if") if k in c}
                       for c in criteria.get("choices", []) + criteria.get("yes_no", [])},
        "photos": photos,
        "expected": expected,
    }
    # "</" inside the JSON would close the <script> tag.
    json_page = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = (PAGE.replace("__SWITCH_CSS__", SWITCH_CSS).replace("__SWITCH_HTML__", SWITCH_HTML)
            .replace("__SWITCH_JS__", switch_js(load_labels()))
            .replace("__EXPORT_NAME__", args.expected.name).replace("__DATA__", json_page))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(f"{len(data['photos'])} photos · page written: {args.output}")


if __name__ == "__main__":
    main()
