"""Measures engines that need NO training against the expected answers (accuracy per criterion).

Engines:
    siglip2   SigLIP 2 zero-shot (prompts of criteria.json, sigmoid / softmax on the logits), CPU
    qwen      Qwen-VL through Ollama, output constrained by a JSON schema, temperature 0
    baseline  CLIP + probes, read from the existing results_*/results.csv (nothing is run)

Usage:
    python measure.py --engine siglip2 --expected expected_2.json expected_3.json expected_4.json expected_A95.json
    python measure.py --engine qwen --expected "expected_*.json" --limit 50
    python measure.py --engine baseline --expected "expected_*.json" --limit 50
    python measure.py --compare        # side by side, on the photos common to all the engines measured

--expected: files or globs; each one is tied to its photo folder by FOLDERS below
(or "expected_X.json=D:/other/folder"). --limit N: N photos per expected file, drawn with a fixed
seed so that every engine measures the same photos.
Writes results_measure/<engine>/results.csv (";" separator, UTF-8 with BOM).
"""

import argparse
import base64
import csv
import glob
import io
import json
import random
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

from analyzer import UNDETERMINED, apply_rules, crop, load_criteria, masked
from test_clip import EXTENSIONS, load_exclusions

HERE = Path(__file__).parent
OUTPUT = HERE / "results_measure"
URBEX = Path("D:/_Urbex")

# expected file stem -> (photo folder, CLIP+probes results folder)
FOLDERS = {
    "expected_2": (URBEX / "_tmpEntrainementMdl_2", None),  # CLIP was never run on this folder with results kept
    "expected_3": (URBEX / "_tmpEntrainementMdl_3", HERE / "results_3"),
    "expected_4": (URBEX / "_tmpEntrainementMdl_4", HERE / "results_4"),
    "expected_A95": (URBEX / "_tmp" / "A95", HERE / "results_A95"),
}
EXCLUDED = {"expected_4": HERE / "duplicates_4.json"}  # copies of photos of folders 2 and 3

SIGLIP_MODEL = "google/siglip2-base-patch16-224"
SIGLIP_REVISION = "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"  # pinned: an upstream change must not move the results
TEXT_LENGTH = 64  # SigLIP was trained with padding="max_length", max_length=64
OLLAMA = "http://127.0.0.1:11434"
QWEN_MODEL = "qwen3-vl:2b"
QWEN_SIZE = 1024  # longest side of the image sent to Qwen
LOAD_SIZE = 1024  # JPEG decoded at this size at least (draft mode): much faster on big photos
SEED = 0

# Extra criterion measured on the same answers as "blurry": the yes/no decided by comparing the sigmoid of
# the "yes" prompts with the one of the "no" prompts, instead of the absolute sigmoid of "yes".
ALIASES = {"blurry_rel": "blurry"}


# ---------------------------------------------------------------- photos and expected answers

def parse_expected(args):
    """[(set name, expected file, photo folder, results folder)] from files, globs and FILE=FOLDER."""
    result = []
    for arg in args:
        arg, _, folder = arg.partition("=")
        files = sorted(glob.glob(arg)) or [arg]
        for f in files:
            path = Path(f)
            if path.stem not in FOLDERS and not folder:
                print(f"ignored: {path.name} (no photo folder known, use {path.name}=FOLDER)")
                continue
            photos, results = FOLDERS.get(path.stem, (None, None))
            result.append((path.stem, path, Path(folder) if folder else photos, results))
    if not result:
        sys.exit("No usable expected file.")
    return result


def select_photos(sources, limit):
    """[(set, relative file, path, expected answers)]: duplicates left out, same random subset for every engine."""
    photos = []
    for name, expected_path, folder, _ in sources:
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        excluded = load_exclusions(EXCLUDED[name]) if name in EXCLUDED else set()
        files = sorted(f for f in expected if f not in excluded and Path(f).suffix.lower() in EXTENSIONS
                       and (folder / f).exists())
        if len(files) < len(expected) - len(excluded):
            print(f"{name}: {len(expected) - len(excluded) - len(files)} photos not found in {folder}")
        if limit and len(files) > limit:
            shuffled = random.Random(SEED).sample(files, len(files))
            files = sorted(shuffled[:limit])  # prefix of one fixed shuffle: a smaller limit is a subset of a larger one
        photos += [(name, f, folder / f, expected[f]) for f in files]
    return photos


def load_image(path):
    image = Image.open(path)
    if image.format == "JPEG":
        image.draft("RGB", (LOAD_SIZE, LOAD_SIZE))  # the decoder halves the size while it stays >= LOAD_SIZE
    return ImageOps.exif_transpose(image).convert("RGB")


# ---------------------------------------------------------------- SigLIP 2

class SigLip:
    def __init__(self, criteria_path):
        import torch
        from transformers import AutoModel, AutoProcessor

        torch.set_num_threads(4)  # 4 physical cores: more threads is slower
        self.torch = torch
        self.yes_no, self.choices, self.rules = load_criteria(criteria_path)
        self.model = AutoModel.from_pretrained(SIGLIP_MODEL, revision=SIGLIP_REVISION).eval()
        self.processor = AutoProcessor.from_pretrained(SIGLIP_MODEL, revision=SIGLIP_REVISION)
        self.scale = self.model.logit_scale.exp().item()
        self.bias = self.model.logit_bias.item()
        self.emb_yes = [(self.prompts(c["yes"]), self.prompts(c["no"])) for c in self.yes_no]
        self.emb_choices = [torch.cat([self.prompts(v) for v in c["options"].values()]) if c["options"] else None
                            for c in self.choices]

    def normalize(self, output):
        emb = output if isinstance(output, self.torch.Tensor) else output.pooler_output
        return emb / emb.norm(dim=-1, keepdim=True)

    def prompts(self, texts):
        # Prompts of one option: embeddings averaged. SigLIP 2 expects lowercase text.
        texts = [texts] if isinstance(texts, str) else texts
        inputs = self.processor(text=[t.lower() for t in texts], return_tensors="pt", padding="max_length",
                                max_length=TEXT_LENGTH, truncation=True)
        with self.torch.inference_mode():
            emb = self.normalize(self.model.get_text_features(**inputs)).mean(dim=0, keepdim=True)
        return emb / emb.norm(dim=-1, keepdim=True)

    def encode(self, image):
        inputs = self.processor(images=image, return_tensors="pt")
        with self.torch.inference_mode():
            return self.normalize(self.model.get_image_features(**inputs))

    def logits(self, emb_image, emb_prompts):
        return self.scale * emb_image @ emb_prompts.T + self.bias

    def analyse(self, image):
        """(predicted values, scores): the logic of Analyzer.analyse, with SigLIP logits."""
        emb_image = self.encode(image)
        crops = {}
        predicted, scores = {}, {}
        for c, emb in zip(self.choices, self.emb_choices):
            if emb is None or masked(c, predicted):
                continue
            if "crop" in c:
                key = str(c["crop"])
                if key not in crops:
                    crops[key] = self.encode(crop(image, c["crop"]))
                logits = self.logits(crops[key], emb)
                if c.get("with_full_image"):  # average of the crop and of the whole image
                    logits = (logits + self.logits(emb_image, emb)) / 2
            else:
                logits = self.logits(emb_image, emb)
            probas = logits.softmax(dim=-1)[0].tolist()
            detail = dict(zip(c["options"], probas))
            winner = max(detail, key=detail.get)
            score = detail[winner]
            if score < c.get("threshold", 0):
                winner = c.get("default", UNDETERMINED)
                score = detail.get(winner, score)
            predicted[c["name"]], scores[c["name"]] = winner, score
        for c, (yes, no) in zip(self.yes_no, self.emb_yes):
            if masked(c, predicted):
                continue
            logit_yes, logit_no = self.logits(emb_image, yes)[0, 0], self.logits(emb_image, no)[0, 0]
            p = self.torch.sigmoid(logit_yes).item()  # absolute probability of "yes"
            low, high = c.get("uncertainty", [0.5, 0.5])
            predicted[c["name"]] = "yes" if p >= high else "no" if p <= low else UNDETERMINED
            scores[c["name"]] = p
            for alias, name in ALIASES.items():
                if name == c["name"]:
                    p_rel = (self.torch.sigmoid(logit_yes) / (self.torch.sigmoid(logit_yes)
                                                              + self.torch.sigmoid(logit_no))).item()
                    predicted[alias] = "yes" if p_rel >= high else "no"
                    scores[alias] = p_rel
        apply_rules(self.rules, predicted)
        return predicted, scores


# ---------------------------------------------------------------- Qwen-VL through Ollama

def ollama(path, payload, timeout=600):
    request = urllib.request.Request(OLLAMA + path, json.dumps(payload).encode(),
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def ollama_model():
    """Digest of the Ollama model, or None if Ollama is not running or the model not pulled."""
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5) as response:
            models = json.load(response)["models"]
    except OSError:
        return None
    return next((m["digest"] for m in models if m["name"] == QWEN_MODEL), None)


def option_text(prompts):
    texts = [prompts] if isinstance(prompts, str) else prompts
    return " / ".join(t.removeprefix("a photo of ").removeprefix("a photo ") for t in texts)


class Qwen:
    def __init__(self, criteria_path):
        self.yes_no, self.choices, self.rules = load_criteria(criteria_path)

    def spec(self, c):
        """(enum of values, instruction line) of a criterion."""
        if "options" in c:
            values = list(c["options"])
            lines = [f"    {v}: {option_text(p)}" for v, p in c["options"].items()]
            if "threshold" in c and "default" not in c and c.get("undetermined", True):
                values.append(UNDETERMINED)
                lines.append(f"    {UNDETERMINED}: none of them fits")
            return values, f'- "{c["name"]}": choose one value.\n' + "\n".join(lines)
        return ["yes", "no", UNDETERMINED], (f'- "{c["name"]}": yes if the photo matches "{option_text(c["yes"])}", '
                                             f'no if it matches "{option_text(c["no"])}", else {UNDETERMINED}.')

    def ask(self, image, criteria):
        specs = {c["name"]: self.spec(c) for c in criteria}
        schema = {"type": "object", "additionalProperties": False, "required": list(specs),
                  "properties": {n: {"type": "string", "enum": values} for n, (values, _) in specs.items()}}
        prompt = ("You classify a photo of a heritage site, an abandoned place or a landscape. "
                  "Answer every criterion with exactly one of its allowed values.\n"
                  + "\n".join(line for _, line in specs.values()))
        image = image.copy()
        image.thumbnail((QWEN_SIZE, QWEN_SIZE))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        reply = ollama("/api/chat", {
            "model": QWEN_MODEL, "stream": False, "think": False, "format": schema,
            "options": {"temperature": 0, "seed": SEED, "num_ctx": 4096, "num_predict": 400},
            "messages": [{"role": "user", "content": prompt,
                          "images": [base64.b64encode(buffer.getvalue()).decode("ascii")]},
                         # closed empty thinking block: the model answers at once (think=false is not enough here)
                         {"role": "assistant", "content": "<think>\n\n</think>\n\n"}],
        })
        content = reply["message"]["content"]
        if not content:  # the model spent its tokens thinking: no answer, counted as undetermined
            print(f"  Qwen gave no answer ({reply.get('done_reason')}, {reply.get('eval_count')} tokens)")
            return {n: UNDETERMINED for n in specs}
        answer = json.loads(content)
        return {n: answer.get(n, UNDETERMINED) for n in specs}

    def analyse(self, image):
        # Photo as a whole in one call (all the criteria, masks applied afterwards); a criterion with a crop
        # (weather: the sky) gets its own call, only when it is not masked.
        everything = self.choices + self.yes_no
        answers = self.ask(image, [c for c in everything if "crop" not in c])
        predicted = {}
        for c in everything:
            if masked(c, predicted):
                continue
            if "crop" in c:
                answers.update(self.ask(crop(image, c["crop"]), [c]))
            predicted[c["name"]] = answers[c["name"]]
        apply_rules(self.rules, predicted)
        return predicted, {}


# ---------------------------------------------------------------- baseline: CLIP + probes

def read_baseline(sources):
    """{(set, file): predicted values} from results_*/results.csv (value columns; empty = hidden criterion)."""
    rows = {}
    for name, _, _, results in sources:
        if results is None or not (results / "results.csv").exists():
            print(f"{name}: no CLIP results available, not measured")
            continue
        with open(results / "results.csv", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f, delimiter=";"):
                rows[(name, row["file"])] = {k: (v or None) for k, v in row.items()
                                             if k not in ("file", "time_ms") and not k.endswith("_score")}
    return rows


# ---------------------------------------------------------------- scores

def score_rows(rows, expected_by_photo, criteria_names):
    """{criterion: {n, ok, undetermined, n_applicable, ok_applicable}} (test_clip.py rule: a criterion hidden
    by except / only_if has the expected answer null, so predicting nothing is right)."""
    table = {}
    for key, predicted in rows.items():
        for name in criteria_names:
            source = ALIASES.get(name, name)
            expected = expected_by_photo.get(key, {})
            if source not in expected or name not in predicted:  # CSV rows: a missing column is not measured
                continue
            t = table.setdefault(name, dict(n=0, ok=0, undetermined=0, n_applicable=0, ok_applicable=0))
            value, wanted = predicted.get(name), expected[source]
            t["n"] += 1
            t["ok"] += value == wanted
            t["undetermined"] += value == UNDETERMINED and wanted != UNDETERMINED
            if wanted is not None:
                t["n_applicable"] += 1
                t["ok_applicable"] += value == wanted
    return table


def pct(a, b):
    return f"{100 * a / b:5.1f}%" if b else "    -"


def print_table(title, table, order):
    print(f"\n{title}")
    print(f"{'criterion':<16}{'n':>6}{'accuracy':>10}{'undet.':>9}{'n appl.':>9}{'acc appl.':>11}")
    for name in order:
        if name in table:
            t = table[name]
            print(f"{name:<16}{t['n']:>6}{pct(t['ok'], t['n']):>10}{pct(t['undetermined'], t['n']):>9}"
                  f"{t['n_applicable']:>9}{pct(t['ok_applicable'], t['n_applicable']):>11}")


def criteria_order(criteria_path):
    yes_no, choices, _ = load_criteria(criteria_path)
    return [c["name"] for c in choices + yes_no] + list(ALIASES)


def read_measure(engine):
    path = OUTPUT / engine / "results.csv"  # engine = engine name or --output-name
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {(r["set"], r["file"]): {k: (v or None) for k, v in r.items()
                                        if k not in ("set", "file", "time_ms") and not k.endswith("_score")
                                        and v != "?"}
                for r in csv.DictReader(f, delimiter=";")}


def expected_of(photos):
    return {(s, f): e for s, f, _, e in photos}


def compare(sources, criteria_path):
    engines = {"CLIP+probes": read_measure("baseline"), "SigLIP 2": read_measure("siglip2"),
               "Qwen": read_measure("qwen")}
    engines = {k: v for k, v in engines.items() if v}
    expected = expected_of(select_photos(sources, 0))
    common = set.intersection(*(set(v) for v in engines.values()))
    print(f"Engines: {', '.join(engines)}; {len(common)} photos in common")
    tables = {}
    for engine, rows in engines.items():
        tables[engine] = score_rows({k: rows[k] for k in common}, expected, criteria_order(criteria_path))
    print(f"\n{'criterion':<16}" + "".join(f"{e:>22}" for e in engines))
    for name in criteria_order(criteria_path):
        cells = []
        for engine in engines:
            t = tables[engine].get(name)
            cells.append(f"{pct(t['ok'], t['n'])} (n={t['n']}, u={pct(t['undetermined'], t['n']).strip()})"
                         if t else "-")
        if any(c != "-" for c in cells):
            print(f"{name:<16}" + "".join(f"{c:>22}" for c in cells))


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="Accuracy per criterion of engines that need no training.")
    parser.add_argument("--engine", choices=["siglip2", "qwen", "baseline"])
    parser.add_argument("--expected", nargs="+", default=["expected_*.json"], help="files or globs")
    parser.add_argument("--criteria", type=Path, default=HERE / "criteria.json")
    parser.add_argument("--output-name", help="results folder name under results_measure/ (default: the engine name)")
    parser.add_argument("--limit", type=int, default=0, help="photos per expected file (0 = all)")
    parser.add_argument("--compare", action="store_true", help="side by side table of the engines already measured")
    parser.add_argument("--resume", action="store_true", help="keep the photos already in the CSV, do the others")
    parser.add_argument("--stop-after", type=int, default=0, help="total number of photos in the CSV to stop at")
    args = parser.parse_args()

    sources = parse_expected(args.expected)
    if args.compare:
        return compare(sources, args.criteria)
    if not args.engine:
        parser.error("--engine or --compare is required")
    photos = select_photos(sources, args.limit)
    expected = expected_of(photos)
    order = criteria_order(args.criteria)
    print(f"{len(photos)} photos")

    name_out = args.output_name or args.engine
    out = OUTPUT / name_out
    out.mkdir(parents=True, exist_ok=True)
    rows, times = {}, []
    if args.engine == "baseline":
        known = read_baseline(sources)
        rows = {(s, f): known[(s, f)] for s, f, _, _ in photos if (s, f) in known}
        names = sorted({n for r in rows.values() for n in r})
    else:
        if args.engine == "qwen":
            digest = ollama_model()
            if digest is None:
                sys.exit(f"Ollama is not running or {QWEN_MODEL} is not pulled: Qwen not measured.")
            print(f"Ollama {QWEN_MODEL}, digest {digest[:12]}")
            engine = Qwen(args.criteria)
        else:
            engine = SigLip(args.criteria)
            print(f"{SIGLIP_MODEL}, revision {SIGLIP_REVISION}")
        names = order if args.engine == "siglip2" else [n for n in order if n not in ALIASES]
        path = out / "results.csv"
        if args.resume and path.exists():
            # Photos already in the file are kept and not redone; --stop-after counts them in the total.
            done = set(read_measure(name_out))
            photos = [p for p in photos if (p[0], p[1]) not in done]
            if args.stop_after:
                photos = photos[:max(0, args.stop_after - len(done))]
            print(f"{len(done)} photos already measured, {len(photos)} to do")
            csv_file = open(path, "a", newline="", encoding="utf-8-sig")
            writer = csv.writer(csv_file, delimiter=";")
        else:
            if args.stop_after:
                photos = photos[:args.stop_after]
            csv_file = open(path, "w", newline="", encoding="utf-8-sig")
            writer = csv.writer(csv_file, delimiter=";")
            writer.writerow(["set", "file", "time_ms"] + [x for n in names for x in (n, n + "_score")])
        start_all = time.perf_counter()
        with ThreadPoolExecutor(2) as pool:  # the next photos are decoded while the current one is analysed
            images = pool.map(lambda p: load_image(p[2]), photos)
            for i, ((s, f, _, _), image) in enumerate(zip(photos, images), 1):
                t0 = time.perf_counter()
                predicted, scores = engine.analyse(image)
                ms = (time.perf_counter() - t0) * 1000
                times.append(ms)
                rows[(s, f)] = predicted
                writer.writerow([s, f, f"{ms:.0f}"] + [x for n in names
                                 for x in (predicted.get(n) or "", f"{scores[n]:.3f}" if n in scores else "")])
                csv_file.flush()
                if i % 50 == 0 or i == len(photos):
                    print(f"[{i}/{len(photos)}] {ms:.0f} ms, elapsed {time.perf_counter() - start_all:.0f} s",
                          flush=True)
        csv_file.close()
        warm = times[1:] or times
        print(f"\nAnalysis time per photo: {sum(warm) / len(warm):.0f} ms (first photo excluded, loading excluded)")
        print(f"Wall time per photo: {(time.perf_counter() - start_all) / len(photos) * 1000:.0f} ms")
    if args.engine == "baseline":
        with open(out / "results.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["set", "file", "time_ms"] + names)
            for (s, f_), predicted in rows.items():
                writer.writerow([s, f_, ""] + ["?" if n not in predicted else predicted[n] or "" for n in names])  # "?": no column in that CLIP run

    rows = read_measure(name_out)  # scored from the file, as compare() does
    print_table(f"{name_out}: all photos", score_rows(rows, expected, order), order)
    for s in sorted({s for s, _ in rows}):
        part = {k: v for k, v in rows.items() if k[0] == s}
        print_table(f"{name_out}: {s} ({len(part)} photos)", score_rows(part, expected, order), order)
    print(f"\nResults: {out / 'results.csv'}")


if __name__ == "__main__":
    main()
