"""CLIP recognition test on a folder of photos.

Usage:
    python test_clip.py FOLDER [--criteria criteria.json] [--expected expected.json]
                        [--probes probes.pt] [--output results] [--recursive]

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

import numpy as np
import torch
from PIL import Image, ImageOps
from transformers import CLIPModel, CLIPProcessor

from labels import SWITCH_CSS, SWITCH_HTML, load_labels, switch_js

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
UNDETERMINED = "undetermined"
THUMBNAIL_SIZE = 320
FIXED_SKY_CROP = (0, 0, 1, 0.3)  # used by the "sky" crop when no sky area is found


def load_criteria(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("yes_no", []), data.get("choices", []), data.get("rules", [])


def normalize(output):
    # transformers >= 5 returns an object whose pooler_output holds the projected embedding;
    # older versions returned the tensor itself.
    emb = output if isinstance(output, torch.Tensor) else output.pooler_output
    return emb / emb.norm(dim=-1, keepdim=True)


@torch.no_grad()
def encode_texts(model, processor, texts, device):
    inputs = processor(text=texts, return_tensors="pt", padding=True).to(device)
    return normalize(model.get_text_features(**inputs))


def encode_prompts(model, processor, prompts, device):
    # One prompt or a list of prompts: their embeddings are averaged,
    # which makes the criterion less sensitive to a particular wording.
    if isinstance(prompts, str):
        prompts = [prompts]
    emb = encode_texts(model, processor, prompts, device).mean(dim=0, keepdim=True)
    return emb / emb.norm(dim=-1, keepdim=True)


@torch.no_grad()
def encode_image(model, processor, image, device):
    inputs = processor(images=image, return_tensors="pt").to(device)
    return normalize(model.get_image_features(**inputs))


def sky_box(image):
    """Box (left, top, right, bottom, as fractions) around the sky in the upper half of the image.

    Sky pixels are blue, or bright and colourless (clouds, haze): trees and walls are left out,
    so a sky partly hidden by foliage is judged on its visible part only.
    """
    small = image.resize((64, max(2, round(64 * image.height / image.width))))
    hue, sat, val = np.asarray(small.convert("HSV"), dtype=np.int16).transpose(2, 0, 1)
    sky = ((hue >= 120) & (hue <= 185) & (sat >= 40) & (val >= 90)) | ((sat < 40) & (val >= 110))
    height = sky.shape[0]
    upper = sky[: height // 2]
    band = upper[: max(1, round(height * 0.3))]
    cols = np.flatnonzero(band.mean(axis=0) >= 0.5)
    if len(cols) < 0.15 * 64:
        return FIXED_SKY_CROP
    left, right = cols[0], cols[-1] + 1
    rows = np.flatnonzero(upper[:, left:right].mean(axis=1) >= 0.5)
    if len(rows) < 0.1 * height:
        return FIXED_SKY_CROP
    return (left / 64, rows[0] / height, right / 64, (rows[-1] + 1) / height)


def crop(image, box):
    if box == "sky":
        box = sky_box(image)
    left, top, right, bottom = box
    return image.crop((int(left * image.width), int(top * image.height),
                       int(right * image.width), int(bottom * image.height)))


def crop_key(box):
    # Name of a crop, for caches: "sky" or "0-0-1-0.3".
    return box if isinstance(box, str) else "-".join(str(v) for v in box)


def thumbnail_base64(image):
    thumb = image.copy()
    thumb.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE))
    buffer = io.BytesIO()
    thumb.save(buffer, format="JPEG", quality=80)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def color(score):
    # red (0) -> green (1)
    return f"hsl({int(score * 120)}, 70%, 40%)"


def combine(emb_crop, emb_image):
    # Cropped area + whole image, concatenated and renormalized ("with_full_image" option).
    emb = torch.cat([emb_crop, emb_image], dim=-1)
    return emb / emb.norm(dim=-1, keepdim=True)


def double_prompts(emb_prompts):
    # Prompts facing combine(): the score is the average of those of the crop and of the whole image.
    return torch.cat([emb_prompts, emb_prompts], dim=-1) / 2 ** 0.5


def masked(criterion, predicted):
    # "except": {"place_type": ["landscape"]} hides the criterion when an earlier result is listed;
    # "only_if": {"place_type": ["vehicle"]} hides it unless an earlier result is listed.
    if any(predicted.get(name) in values for name, values in criterion.get("except", {}).items()):
        return True
    return any(predicted.get(name) not in values for name, values in criterion.get("only_if", {}).items())


def apply_rules(rules, predicted):
    # {"if": {"place_type": ["wall"], "graffiti": ["yes"]}, "set": {"place_type": "street_art"}}
    changed = {}
    for rule in rules:
        if all(predicted.get(name) in values for name, values in rule["if"].items()):
            changed.update(rule["set"])
    predicted.update(changed)
    return changed


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


class Analyzer:
    """CLIP model, prompts and probes, loaded once; analyse() runs every criterion on one image."""

    def __init__(self, criteria_path, probes_path, model_name="openai/clip-vit-base-patch16"):
        self.yes_no, self.choices, self.rules = load_criteria(criteria_path)
        self.shown = [c for c in self.choices + self.yes_no if not c.get("hidden")]
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading {model_name} on {self.device} (downloaded on first run)…")
        t0 = time.perf_counter()
        self.model = CLIPModel.from_pretrained(model_name).to(self.device).eval()
        self.processor = CLIPProcessor.from_pretrained(model_name)
        self.scale = self.model.logit_scale.exp()
        print(f"Model loaded in {time.perf_counter() - t0:.1f} s")
        self.probes = {}
        if any(c.get("probe") for c in self.choices):
            if not Path(probes_path).exists():
                sys.exit(f"{probes_path} not found: run train_probes.py first")
            self.probes = {name: p for name, p in torch.load(probes_path).items()
                           if any(c["name"] == name and c.get("probe") for c in self.choices)}
            print(f"Probes used: {', '.join(self.probes)}")

        # The prompts do not change from one image to the next: they are encoded once.
        def prompts(texts):
            return encode_prompts(self.model, self.processor, texts, self.device)

        self.emb_yes_no = [torch.cat([prompts(c[side]) for side in ("yes", "no")]) for c in self.yes_no]
        # A criterion without options yet ("free": values added in the review page) has no prompts.
        self.emb_choices = [torch.cat([prompts(v) for v in c["options"].values()]) if c["options"] else None
                            for c in self.choices]
        self.emb_choices = [double_prompts(e) if "crop" in c and c.get("with_full_image") else e
                            for c, e in zip(self.choices, self.emb_choices)]

    def analyse(self, image, all_details=False):
        """Returns (results, details, predicted) for one RGB image.

        results[name] = (value, score), or None for a criterion hidden by "except" / "only_if";
        details[name] = score of each option; predicted[name] = value, rules applied.
        all_details: the hidden choices are scored too (details only), so that a form can
        offer them when the user changes an earlier answer.
        """
        emb_img = encode_image(self.model, self.processor, image, self.device)
        emb_crops = {}  # a crop is encoded once per image
        # The choices come first (in file order): the following criteria
        # can be hidden depending on their result, with "except" and "only_if".
        predicted = {}
        results, details = {}, {}
        for c, emb in zip(self.choices, self.emb_choices):
            hidden = masked(c, predicted)
            results[c["name"]] = None
            # No options: not assessed by CLIP (result None, as for a hidden criterion).
            if (hidden and not all_details) or emb is None:
                continue
            emb_area = emb_img
            if "crop" in c:
                # "sky" (found in the image) or [left, top, right, bottom] as fractions of the image.
                key = crop_key(c["crop"])
                if key not in emb_crops:
                    emb_crops[key] = encode_image(self.model, self.processor, crop(image, c["crop"]), self.device)
                emb_area = emb_crops[key]
                if c.get("with_full_image"):
                    emb_area = combine(emb_area, emb_img)
            if c["name"] in self.probes:
                # Probe learnt by train_probes.py instead of the prompts.
                probe = self.probes[c["name"]]
                probas = (self.scale * emb_area @ probe["W"] + probe["b"]).softmax(dim=-1)[0].tolist()
                detail = dict(zip(probe["classes"], probas))
            else:
                probas = (self.scale * emb_area @ emb.T).softmax(dim=-1)[0].tolist()
                detail = dict(zip(c["options"].keys(), probas))
            details[c["name"]] = detail
            if hidden:
                continue
            winner = max(detail, key=detail.get)
            score = detail[winner]
            # No option convincing enough: fall back on "default", otherwise do not decide.
            if score < c.get("threshold", 0):
                winner = c.get("default", UNDETERMINED)
                score = detail.get(winner, score)
            results[c["name"]] = (winner, score)
            predicted[c["name"]] = winner
        for c, emb in zip(self.yes_no, self.emb_yes_no):
            if masked(c, predicted):
                results[c["name"]] = None
                continue
            p = (self.scale * emb_img @ emb.T).softmax(dim=-1)[0][0].item()
            # Between the two "uncertainty" bounds, no guess is made.
            low, high = c.get("uncertainty", [0.5, 0.5])
            value = "yes" if p >= high else "no" if p <= low else UNDETERMINED
            results[c["name"]] = (value, p)
            predicted[c["name"]] = value
        for name, value in apply_rules(self.rules, predicted).items():
            results[name] = (value, results[name][1])
        return results, details, predicted


def main():
    parser = argparse.ArgumentParser(description="Runs CLIP on a folder of photos.")
    parser.add_argument("folder", type=Path, help="folder containing the photos")
    parser.add_argument("--criteria", type=Path, default=Path(__file__).with_name("criteria.json"))
    parser.add_argument("--expected", type=Path, default=Path(__file__).with_name("expected.json"),
                        help="expected answers per photo, to measure the errors")
    parser.add_argument("--probes", type=Path, default=Path(__file__).with_name("probes.pt"),
                        help="probes learnt by train_probes.py, for the criteria marked \"probe\"")
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--model", default="openai/clip-vit-base-patch16")
    parser.add_argument("--recursive", action="store_true", help="include subfolders")
    args = parser.parse_args()

    pattern = "**/*" if args.recursive else "*"
    images = sorted(p for p in args.folder.glob(pattern) if p.suffix.lower() in EXTENSIONS)
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
    write_html(args.output / "results.html", rows, shown, summary, load_labels())

    for key, values in summary:
        print(key, values)
    print(f"Results: {args.output / 'results.csv'} and {args.output / 'results.html'}")


if __name__ == "__main__":
    main()
