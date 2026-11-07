"""CLIP recognition test on a folder of photos.

Usage:
    python test_clip.py FOLDER [--criteria criteria.json] [--expected expected.json]
                        [--probes probes.pt] [--output results] [--recursive]
                        [--exclude duplicates_4.json]

Writes results/results.csv and results/results.html (thumbnails, scores, FR/EN switch).
"""

import argparse
import base64
import csv
import html
import io
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageOps

from analyzer import CLIP_MODEL, UNDETERMINED, Analyzer
from labels import SWITCH_CSS, SWITCH_HTML, load_labels, switch_js

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
THUMBNAIL_SIZE = 320


def thumbnail_base64(image):
    thumb = image.copy()
    thumb.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE))
    buffer = io.BytesIO()
    thumb.save(buffer, format="JPEG", quality=80)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def color(score):
    # red (0) -> green (1)
    return f"hsl({int(score * 120)}, 70%, 40%)"


def check_mark(row, name):
    # CSS class and expected value, when the photo is listed in the expected answers file.
    if name not in row["check"]:
        return "", ""
    expected, ok = row["check"][name]
    if ok:
        return ' class="ok"', ""
    # The label of the expected value is filled in by translateCards() in the page.
    value = "" if expected is None else f' data-v="{html.escape(name)}:{html.escape(expected)}"'
    return ' class="wrong"', f' <small class="expected"{value}></small>'


def write_html(path, rows, criteria, summary, labels):
    cards = []
    for row in rows:
        items = []
        for c in criteria:
            name = c["name"]
            css, expected = check_mark(row, name)
            label = f'<span><span data-t="c:{html.escape(name)}">{html.escape(name)}</span>{expected}</span>'
            result = row["results"][name]
            if result is None:
                items.append(f"<li{css}>{label}<b>—</b></li>")
                continue
            value, p = result
            detail = row["details"].get(name)
            attributes = "" if not detail else f' data-detail="{html.escape(json.dumps(detail))}"'
            style = "" if detail else f' style="color:{color(p)}"'
            items.append(
                f'<li{css}{attributes} data-name="{html.escape(name)}">{label}'
                f'<b{style}><span data-t="v:{html.escape(name)}:{html.escape(value)}">{html.escape(value)}</span>'
                f" {p:.0%}</b></li>"
            )
        cards.append(
            f'<div class="card"><img src="data:image/jpeg;base64,{row["thumbnail"]}" alt="" '
            f'data-full="{html.escape(row["uri"])}" data-t-title="ui:enlarge">'
            f'<div class="name">{html.escape(row["file"])} '
            f'<small>{row["time_ms"]:.0f} ms</small></div><ul>{"".join(items)}</ul></div>'
        )
    summary_html = "".join(
        f'<span data-t="ui:{key}" data-vars="{html.escape(json.dumps(values))}"></span>'
        for key, values in summary
    )

    page = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CLIP results</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 16px; background: #f4f4f4; color: #222; }}
  h1 {{ display: flex; gap: 16px; align-items: center; }}
  .infos {{ margin-bottom: 16px; }}
  .infos span + span::before {{ content: " · "; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }}
  .card {{ background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px #0002; }}
  .card img {{ width: 100%; height: 200px; object-fit: cover; display: block; cursor: zoom-in; }}
  .name {{ padding: 6px 10px; font-weight: 600; word-break: break-all; }}
  .name small {{ font-weight: normal; color: #888; }}
  ul {{ list-style: none; margin: 0; padding: 0 10px 10px; font-size: 14px; }}
  li {{ display: flex; justify-content: space-between; gap: 6px; border-top: 1px solid #eee; padding: 3px 0; }}
  li.ok {{ background: #e3f6e3; }}
  li.wrong {{ background: #fbe0e0; }}
  #viewer {{ position: fixed; inset: 0; background: #000e; display: none;
            flex-direction: column; align-items: center; justify-content: center; gap: 10px; }}
  #viewer.open {{ display: flex; }}
  #viewer img {{ max-width: 96vw; max-height: 86vh; object-fit: contain; }}
  #viewer button {{ font-size: 16px; padding: 8px 20px; cursor: pointer; }}
  #viewer .caption {{ color: #ddd; font-size: 14px; }}
{SWITCH_CSS}
</style></head><body>
<h1><span data-t="ui:results_title">CLIP results</span> {SWITCH_HTML}</h1>
<p class="infos">{summary_html}<br><span data-t="ui:results_help"></span></p>
<div class="grid">{"".join(cards)}</div>
<div id="viewer">
  <button id="back" data-t="ui:back">← Back</button>
  <img alt="">
  <div class="caption"></div>
</div>
<script>
{switch_js(labels)}
function translateCards() {{
  // Expected value of a wrong answer, and score of every option in the tooltip.
  for (const el of document.querySelectorAll("small.expected")) {{
    const value = el.dataset.v ? t("v:" + el.dataset.v) : "—";
    el.textContent = " (" + t("ui:expected", {{ value }}) + ")";
  }}
  for (const li of document.querySelectorAll("li[data-detail]")) {{
    li.title = Object.entries(JSON.parse(li.dataset.detail))
      .map(([v, p]) => t("v:" + li.dataset.name + ":" + v) + " " + Math.round(p * 100) + " %").join(" · ");
  }}
}}
onLanguageChange = translateCards;
translate(); translateCards();
const viewer = document.getElementById("viewer");
const large = viewer.querySelector("img");
const caption = viewer.querySelector(".caption");
function closeViewer() {{ viewer.classList.remove("open"); large.removeAttribute("src"); }}
document.querySelector(".grid").addEventListener("click", e => {{
  const thumb = e.target.closest(".card img");
  if (!thumb) return;
  large.src = thumb.dataset.full;
  caption.textContent = thumb.parentElement.querySelector(".name").textContent;
  viewer.classList.add("open");
}});
document.getElementById("back").addEventListener("click", closeViewer);
viewer.addEventListener("click", e => {{ if (e.target === viewer) closeViewer(); }});
document.addEventListener("keydown", e => {{ if (e.key === "Escape") closeViewer(); }});
</script>
</body></html>"""
    path.write_text(page, encoding="utf-8")




def load_exclusions(path):
    """Photos to leave out (paths relative to their folder): the keys of a JSON object, or a JSON list."""
    with open(path, encoding="utf-8") as f:
        return set(json.load(f))


def main():
    parser = argparse.ArgumentParser(description="Runs CLIP on a folder of photos.")
    parser.add_argument("folder", type=Path, help="folder containing the photos")
    parser.add_argument("--criteria", type=Path, default=Path(__file__).with_name("criteria.json"))
    parser.add_argument("--expected", type=Path, default=Path(__file__).with_name("expected.json"),
                        help="expected answers per photo, to measure the errors")
    parser.add_argument("--probes", type=Path, default=Path(__file__).with_name("probes.pt"),
                        help="probes learnt by train_probes.py, for the criteria marked \"probe\"")
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--model", default=CLIP_MODEL)
    parser.add_argument("--recursive", action="store_true", help="include subfolders")
    parser.add_argument("--exclude", type=Path,
                        help="JSON file whose keys (or items) are photos to leave out, e.g. duplicates_4.json")
    parser.add_argument("--no-html", action="store_true", help="write results.csv only, without the results page")
    args = parser.parse_args()

    pattern = "**/*" if args.recursive else "*"
    excluded = load_exclusions(args.exclude) if args.exclude else set()
    found = sorted(p for p in args.folder.glob(pattern) if p.suffix.lower() in EXTENSIONS)
    images = [p for p in found if p.relative_to(args.folder).as_posix() not in excluded]
    if excluded:
        print(f"{len(found) - len(images)} photos left out ({args.exclude.name})")
    if not images:
        sys.exit(f"No image found in {args.folder}")

    expected_answers = {}
    if args.expected.exists():
        with open(args.expected, encoding="utf-8") as f:
            expected_answers = json.load(f)
    analyzer = Analyzer(args.criteria, args.probes, args.model)
    shown = analyzer.shown

    rows = []
    for i, path in enumerate(images, 1):
        try:
            image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        except Exception as e:
            print(f"[{i}/{len(images)}] {path.name}: unreadable ({e})")
            continue

        start = time.perf_counter()
        results, details, predicted = analyzer.analyse(image)
        time_ms = (time.perf_counter() - start) * 1000

        file = path.relative_to(args.folder).as_posix()
        check = {name: (value, predicted.get(name) == value)
                 for name, value in expected_answers.get(file, {}).items()
                 if any(c["name"] == name for c in shown)}

        rows.append({
            "file": file,
            "uri": path.resolve().as_uri(),  # original image, shown full size in the HTML
            "time_ms": time_ms,
            "results": results,
            "details": details,
            "check": check,
            "thumbnail": thumbnail_base64(image),
        })
        print(f"[{i}/{len(images)}] {path.name}: {time_ms:.0f} ms")

    if not rows:
        sys.exit("No image could be analysed.")

    args.output.mkdir(parents=True, exist_ok=True)

    # CSV in UTF-8 with BOM and ";" separator so that Excel (French) opens it correctly.
    # Each criterion takes two columns: the value and its score (for yes/no, the probability of "yes").
    header = ["file", "time_ms"]
    for c in shown:
        header += [c["name"], f'{c["name"]}_score']
    with open(args.output / "results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        for r in rows:
            line = [r["file"], f'{r["time_ms"]:.0f}']
            for c in shown:
                res = r["results"][c["name"]]
                line += ["", ""] if res is None else [res[0], f"{res[1]:.3f}"]
            w.writerow(line)

    # The first image often includes a warm-up time: it is left out of the average when possible.
    times = [r["time_ms"] for r in rows]
    average = sum(times[1:]) / (len(times) - 1) if len(times) > 1 else times[0]
    summary = [("summary", {"n": len(rows), "model": args.model, "device": analyzer.device,
                             "ms": f"{average:.0f}"})]
    checks = [(r, name, expected, ok) for r in rows for name, (expected, ok) in r["check"].items()]
    if checks:
        right = sum(ok for *_, ok in checks)

        def prediction(row, name):
            return None if row["results"][name] is None else row["results"][name][0]

        # "undetermined" given instead of a real value: not an error, an absence of answer.
        no_answer = sum(not ok and prediction(r, name) == UNDETERMINED for r, name, _, ok in checks)
        summary.append(("check", {"ok": right, "total": len(checks), "undetermined": no_answer,
                                  "wrong": len(checks) - right - no_answer}))
        for r, name, expected, ok in checks:
            if not ok and prediction(r, name) != UNDETERMINED:
                print(f"  ✗ {r['file']} {name}: expected {expected or '— (not applicable)'}, "
                      f"got {prediction(r, name) or '—'}")
    if not args.no_html:
        write_html(args.output / "results.html", rows, shown, summary, load_labels())

    for key, values in summary:
        print(key, values)
    print(f"Results: {args.output}")


if __name__ == "__main__":
    main()
