"""Learns "probes": one small linear layer per criterion, on top of the CLIP embedding of the image.

Each probe starts from the prompts of criteria.json (the "zero-shot" classification) and only moves
away from them where the expected answers justify it: an option without example is still
recognised by its prompt. An expected "undetermined" answer becomes a learnt class of its own.

Usage:
    python train_probes.py --data FOLDER EXPECTED [--data FOLDER EXPECTED ...] [--evaluate]
                           [--exclude FOLDER duplicates_4.json] [--places places.json]

Several folders can be combined (subfolders included: the keys of the expected files are
relative paths). --evaluate measures with cross-validation (each photo judged by a probe that
has not seen it) instead of saving the probes in probes.pt.

Photos of one place stay in the same fold: otherwise a probe is judged on near copies of what it
learnt, and the score is too high. The place comes from places.json (file name -> marker_id, only
for names that designate one marker), then from the subfolder, then from the visit (photos shot
less than SESSION_GAP apart).
"""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

import torch
from PIL import Image, ImageOps

from analyzer import (CLIP_MODEL, UNDETERMINED, clip_revision, combine, crop, crop_key, double_prompts,
                      encode_image, encode_prompts, load_clip)
from photo_exif import read_exif
from test_clip import load_exclusions

FOLDS = 5
REGULARIZATIONS = [0.01, 0.1, 1.0]  # strength of the pull towards the prompts, chosen by cross-validation
SESSION_GAP = timedelta(hours=3)  # two shots closer than this: same visit
CACHE = Path(__file__).with_name(".cache")


def cache_path(model_name, folder, box=None):
    # The key holds the model and the full path: embeddings of another model or of another
    # folder with the same name must never be reused.
    key = hashlib.sha1(f"{model_name}@{clip_revision(model_name)}|{folder.resolve()}".encode()).hexdigest()[:8]
    suffix = "" if box is None else "_" + crop_key(box)
    return CACHE / f"embeddings_{folder.name}_{key}{suffix}.pt"


def embeddings(model, processor, folder, files, box=None):
    """CLIP embeddings of the images (or of a crop, as in test_clip.py), cached per model, folder and crop."""
    suffix = "" if box is None else "_" + crop_key(box)
    cache = cache_path(model.name_or_path, folder, box)
    known = torch.load(cache) if cache.exists() else {}
    missing = [f for f in files if f not in known]
    for i, f in enumerate(missing, 1):
        image = ImageOps.exif_transpose(Image.open(folder / f)).convert("RGB")
        if box is not None:
            image = crop(image, box)
        known[f] = encode_image(model, processor, image, "cpu")[0]
        if i % 50 == 0:
            print(f"  embeddings {folder.name}{suffix}: {i}/{len(missing)}")
    if missing:
        CACHE.mkdir(parents=True, exist_ok=True)
        torch.save(known, cache)
    return torch.stack([known[f] for f in files])


def place_groups(photos, places):
    """{(folder, file): group}. The marker when known; otherwise the main place of the photo's subfolder,
    then of its visit; otherwise the subfolder or the visit itself.

    A visit never merges two known places: chained together, they would make one giant group.
    """
    groups = {photo: places.get(Path(photo[1]).name) for photo in photos}

    def spread(clusters):
        for key, cluster in clusters.items():
            known = Counter(groups[p] for p in cluster if groups[p] is not None)
            main = known.most_common(1)[0][0] if known else key
            for photo in cluster:
                if groups[photo] is None:
                    groups[photo] = main

    subfolders = defaultdict(list)
    for photo in photos:
        if len(Path(photo[1]).parts) > 1:
            subfolders[(photo[0], Path(photo[1]).parent)].append(photo)
    spread(subfolders)

    shots = []
    for photo in photos:
        taken = read_exif(photo[0] / photo[1])["taken"]
        if taken:
            shots.append((taken.replace(tzinfo=None), photo))  # camera time: some have an offset, others not
    shots.sort(key=lambda shot: shot[0])
    visits = defaultdict(list)
    visit, last = None, None
    for taken, photo in shots:
        if last is None or taken - last >= SESSION_GAP:
            visit = ("visit", taken)
        visits[visit].append(photo)
        last = taken
    spread(visits)
    return {photo: photo if group is None else group for photo, group in groups.items()}


def assign_folds(groups):
    """{photo: fold}: a whole group goes to one fold, the largest groups first, to balance them."""
    sizes = Counter(groups.values())
    fold_sizes = [0] * FOLDS
    fold_of_group = {}
    for group, size in sorted(sizes.items(), key=lambda item: (-item[1], str(item[0]))):
        fold = fold_sizes.index(min(fold_sizes))
        fold_of_group[group] = fold
        fold_sizes[fold] += size
    return {photo: fold_of_group[group] for photo, group in groups.items()}


def train(X, y, W0, scale, lam):
    """Logistic regression whose weights are pulled towards W0 (the prompts) with strength lam."""
    W = W0.clone().requires_grad_(True)
    b = torch.zeros(W0.shape[1], requires_grad=True)
    opt = torch.optim.LBFGS([W, b], max_iter=300, line_search_fn="strong_wolfe")

    def loss():
        opt.zero_grad()
        value = torch.nn.functional.cross_entropy(scale * X @ W + b, y) + lam * ((W - W0) ** 2).sum()
        value.backward()
        return value

    opt.step(loss)
    return W.detach(), b.detach()


def rule_sources(rules):
    # A value set by a rule is learnt as the value the rule starts from (street_art -> wall).
    sources = {}
    for rule in rules:
        for name, value in rule["set"].items():
            if name in rule["if"] and len(rule["if"][name]) == 1:
                sources[(name, value)] = rule["if"][name][0]
    return sources


def main():
    parser = argparse.ArgumentParser(description="Learns the linear probes of the criteria marked \"probe\".")
    parser.add_argument("--data", nargs=2, action="append", required=True, metavar=("FOLDER", "EXPECTED"),
                        help="photo folder and its expected answers file (repeatable)")
    parser.add_argument("--criteria", type=Path, default=Path(__file__).with_name("criteria.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("probes.pt"))
    parser.add_argument("--model", default=CLIP_MODEL)
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--exclude", nargs=2, action="append", default=[], metavar=("FOLDER", "EXCLUDE"),
                        help="photos of FOLDER to leave out, listed in a JSON file such as duplicates_4.json (repeatable)")
    parser.add_argument("--places", type=Path, default=Path(__file__).with_name("places.json"),
                        help="photo file name -> marker_id, to keep the photos of a place in the same fold")
    args = parser.parse_args()
    excluded = {Path(folder).resolve(): load_exclusions(path) for folder, path in args.exclude}

    with open(args.criteria, encoding="utf-8") as f:
        all_criteria = json.load(f)
    criteria = [c for c in all_criteria["choices"] if c.get("probe")]
    sources = rule_sources(all_criteria.get("rules", []))
    datasets = []
    for folder, expected_path in args.data:
        with open(expected_path, encoding="utf-8") as f:
            expected = json.load(f)
        left_out = excluded.get(Path(folder).resolve(), set())
        datasets.append((Path(folder), sorted(set(expected) - left_out), expected))

    places = json.loads(args.places.read_text(encoding="utf-8")) if args.places.exists() else {}
    groups = place_groups([(folder, f) for folder, files, _ in datasets for f in files], places)
    fold_of = assign_folds(groups)
    fold_sizes = Counter(fold_of.values())
    print(f"{len(fold_of)} photos, {len(set(groups.values()))} groups of photos, "
          f"largest {max(Counter(groups.values()).values())}, folds {sorted(fold_sizes.values())}")

    model, processor = load_clip(args.model)
    scale = model.logit_scale.exp().item()
    probes = {}
    for c in criteria:
        name, box = c["name"], c.get("crop")
        classes = list(c["options"])

        def answer(expected, f):
            value = expected[f].get(name)
            return sources.get((name, value), value)

        # The classes: those of criteria.json, plus "undetermined" if it appears in the answers.
        if c.get("undetermined", True) and any(answer(e, f) == UNDETERMINED for _, files, e in datasets for f in files):
            classes.append(UNDETERMINED)
        prompts = [encode_prompts(model, processor, v, "cpu")[0] for v in c["options"].values()]
        if UNDETERMINED in classes:
            prompts.append(torch.zeros_like(prompts[0]))  # no prompt: learnt from the examples only
        W0 = torch.stack(prompts, dim=1)
        if box is not None and c.get("with_full_image"):
            W0 = double_prompts(W0.T).T.contiguous()  # LBFGS needs contiguous weights

        X, y, folds = [], [], []
        for folder, files, expected in datasets:
            kept = [f for f in files if answer(expected, f) in classes]
            if not kept:
                continue
            E = embeddings(model, processor, folder, kept, box)
            if box is not None and c.get("with_full_image"):
                E = combine(E, embeddings(model, processor, folder, kept))
            X.append(E)
            y += [classes.index(answer(expected, f)) for f in kept]
            folds += [fold_of[(folder, f)] for f in kept]
        X, y, folds = torch.cat(X), torch.tensor(y), torch.tensor(folds)

        def cross_validation(lam):
            pred = torch.empty_like(y)
            for k in range(FOLDS):
                learn, check = folds != k, folds == k
                W, b = train(X[learn], y[learn], W0, scale, lam)
                pred[check] = (scale * X[check] @ W + b).argmax(-1)
            return (pred == y).float().mean().item()

        scores = {lam: cross_validation(lam) for lam in REGULARIZATIONS}
        lam = max(scores, key=scores.get)
        zero_shot = ((scale * X @ W0).argmax(-1) == y).float().mean().item()
        print(f"{name:20} {len(y)} examples · prompts only {zero_shot:.1%} · probe "
              + " · ".join(f"λ={l} {s:.1%}" for l, s in scores.items()))

        if not args.evaluate:
            W, b = train(X, y, W0, scale, lam)
            probes[name] = {"classes": classes, "W": W, "b": b, "lambda": lam}

    if not args.evaluate:
        torch.save(probes, args.output)
        print(f"Probes saved: {args.output} ({', '.join(probes)})")


if __name__ == "__main__":
    main()
