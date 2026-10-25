"""FR/EN display labels (labels.json), shared by the results page and the review page.

The code and the JSON files use English keys only; labels.json maps each key to its French
and English label. The pages show one language or the other with a switch.
"""

import json
from pathlib import Path

LABELS_PATH = Path(__file__).with_name("labels.json")


def load_labels(path=LABELS_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


SWITCH_CSS = """
  .lang { display: inline-flex; border: 1px solid #aaa; border-radius: 4px; overflow: hidden; }
  .lang button { border: 0; padding: 3px 10px; cursor: pointer; background: #fff; font: inherit; }
  .lang button:disabled { background: #333; color: #fff; cursor: default; }
"""

SWITCH_HTML = '<span class="lang"><button data-lang="fr">FR</button><button data-lang="en">EN</button></span>'

# Every element with data-t="c:criterion", "v:criterion:value" or "ui:key" gets its text from LABELS;
# data-vars (JSON) fills the {placeholders}, data-t-title does the same for the tooltip.
# Unknown keys are shown as is. The chosen language is remembered by the browser.
SWITCH_JS = """
const LABELS = __LABELS__;
let lang = "fr";
try { lang = localStorage.getItem("clip-lang") || "fr"; } catch (e) {}
function label(key) {
  const [kind, a, b] = key.split(":");
  if (kind === "c") return LABELS.criteria[a];
  if (kind === "v") return (LABELS.values[a] || {})[b] || LABELS.values["*"][b];
  return LABELS.ui[a];
}
function t(key, vars) {
  const entry = label(key);
  let text = entry ? (entry[lang] ?? entry.en) : key.split(":").pop();
  for (const [k, v] of Object.entries(vars || {})) text = text.replaceAll("{" + k + "}", v);
  return text;
}
const varsOf = el => el.dataset.vars ? JSON.parse(el.dataset.vars) : undefined;
function translate(root = document) {
  document.documentElement.lang = lang;
  for (const el of root.querySelectorAll("[data-t]")) el.textContent = t(el.dataset.t, varsOf(el));
  for (const el of root.querySelectorAll("[data-t-title]")) el.title = t(el.dataset.tTitle, varsOf(el));
  for (const b of document.querySelectorAll("[data-lang]")) b.disabled = b.dataset.lang === lang;
}
let onLanguageChange = () => {};
for (const b of document.querySelectorAll("[data-lang]")) b.onclick = () => {
  lang = b.dataset.lang;
  try { localStorage.setItem("clip-lang", lang); } catch (e) {}
  translate(); onLanguageChange();
};
"""


def switch_js(labels):
    # "</" inside the JSON would close the <script> tag.
    return SWITCH_JS.replace("__LABELS__", json.dumps(labels, ensure_ascii=False).replace("</", "<\\/"))
