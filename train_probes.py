"""Learns "probes": one small linear layer per criterion, on top of the CLIP embedding of the image.

Each probe starts from the prompts of criteria.json (the "zero-shot" classification) and only moves
away from them where the expected answers justify it: an option without example is still
recognised by its prompt. An expected "undetermined" answer becomes a learnt class of its own.

Usage:
    python train_probes.py --data FOLDER EXPECTED [--data FOLDER EXPECTED ...] [--evaluate]
                           [--exclude FOLDER duplicates_4.json]

Several folders can be combined (subfolders included: the keys of the expected files are
relative paths). --evaluate measures with cross-validation (each photo judged by a probe that
has not seen it) instead of saving the probes in probes.pt.
"""

import argparse
import json
from pathlib import Path

import torch
from PIL import Image, ImageOps
from transformers import CLIPModel, CLIPProcessor

from test_clip import (UNDETERMINED, combine, crop, crop_key, double_prompts, encode_image, encode_prompts,
                       load_exclusions)

FOLDS = 5
REGULARIZATIONS = [0.01, 0.1, 1.0]  # strength of the pull towards the prompts, chosen by cross-validation
CACHE = Path(__file__).with_name(".cache")


def embeddings(model, processor, folder, files, box=None):
    """CLIP embeddings of the images (or of a crop, as in test_clip.py), cached per folder and crop."""
    suffix = "" if box is None else "_" + crop_key(box)
    cache = CACHE / f"embeddings_{folder.name}{suffix}.pt"
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
    parser.add_argument("--model", default="openai/clip-vit-base-patch16")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--exclude", nargs=2, action="append", default=[], metavar=("FOLDER", "EXCLUDE"),
                        help="photos of FOLDER to leave out, listed in a JSON file such as duplicates_4.json (repeatable)")
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

    model = CLIPModel.from_pretrained(args.model).eval()
    processor = CLIPProcessor.from_pretrained(args.model)
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

        X, y = [], []
        for folder, files, expected in datasets:
            kept = [f for f in files if answer(expected, f) in classes]
            if not kept:
                continue
            E = embeddings(model, processor, folder, kept, box)
            if box is not None and c.get("with_full_image"):
                E = combine(E, embeddings(model, processor, folder, kept))
            X.append(E)
            y += [classes.index(answer(expected, f)) for f in kept]
        X, y = torch.cat(X), torch.tensor(y)
        folds = torch.arange(len(y)) % FOLDS

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
