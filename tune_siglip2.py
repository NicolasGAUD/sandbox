"""Fast prompt iteration for SigLIP 2: image embeddings cached once, only the text is re-encoded.

    python tune_siglip2.py --criteria criteria_siglip2.json            # dev set (expected_2, 3, 4) only
    python tune_siglip2.py --criteria criteria_siglip2.json --test     # also the held-out set (expected_A95)
    python tune_siglip2.py --extract                                    # fill the cache (done once)

Needs PYTHONPATH=D:/_Urbex/myurbex/myurbex-ai (analyzer.py) and the myurbex-ai venv.
"""
import argparse
import collections
import pickle
import sys
from pathlib import Path

import measure
from measure import ALIASES, SigLip, UNDETERMINED, load_image, parse_expected, score_rows, select_photos

CACHE = measure.OUTPUT / "cache" / "siglip2_image_features.pkl"
DEV = ["expected_2", "expected_3", "expected_4"]
TEST = ["expected_A95"]


class Tracked:
    """Image stand-in: same width/height/crop as PIL, remembers which photo and which crop it is."""

    def __init__(self, key, image):
        self.key, self.image = key, image
        self.width, self.height = image.width, image.height

    def crop(self, box):
        return Tracked(self.key + (box,), self.image.crop(box))


class CachedSigLip(SigLip):
    def __init__(self, criteria, cache, extract=False):
        super().__init__(criteria)
        self.cache, self.extract = cache, extract

    def encode(self, image):
        if image.key not in self.cache:
            if not self.extract:
                raise KeyError(image.key)
            self.cache[image.key] = super().encode(image.image)
        return self.cache[image.key]


def load_cache():
    return pickle.loads(CACHE.read_bytes()) if CACHE.exists() else {}


def predict(engine, photos, cache):
    rows = {}
    for s, f, path, _ in photos:
        image = Tracked((s, f), load_image(path)) if engine.extract else Tracked((s, f), _Stub(cache, s, f))
        predicted, _ = engine.analyse(image)
        rows[(s, f)] = predicted
    return rows


class _Stub:
    """Size only (taken from the cache) so that no JPEG is decoded during a tuning run."""

    def __init__(self, cache, s, f):
        self.width, self.height = cache[("size", s, f)]

    def crop(self, box):
        return self


def report(rows, photos, names, sets, title):
    sel = {k: v for k, v in rows.items() if k[0] in sets}
    expected = measure.expected_of(photos)
    full = {k: {n: v.get(n) for n in names} for k, v in sel.items()}  # hidden criterion = None, as in the CSV
    table = score_rows(full, expected, names)
    print(f"\n== {title} ({len(sel)} photos)")
    print(" ".join(f"{n}={100 * t['ok'] / t['n']:.1f}" for n, t in table.items() if t["n"]))
    return full, expected


def confusion(full, expected, name, top=14):
    pairs = collections.Counter()
    support = collections.Counter()
    ok = collections.Counter()
    for k, p in full.items():
        want = expected[k].get(name)
        support[want] += 1
        ok[want] += p.get(name) == want
        if p.get(name) != want:
            pairs[(want, p.get(name))] += 1
    print(f"-- {name}: per class (ok/n)")
    print("  ".join(f"{c}:{ok[c]}/{support[c]}" for c in sorted(support, key=lambda c: -support[c]) if c))
    print(f"-- top confusions (expected -> predicted)")
    print("  ".join(f"{a}->{b}:{n}" for (a, b), n in pairs.most_common(top)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--criteria", type=Path, default=measure.HERE / "criteria_siglip2.json")
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--test", action="store_true", help="also report the held-out set")
    ap.add_argument("--confusion", nargs="*", default=["place_type"])
    args = ap.parse_args()
    sources = parse_expected(["expected_*.json"])
    photos = select_photos(sources, 200)  # same 800 photos as the measure.py runs (--limit 200)
    cache = load_cache()
    if args.extract:
        engine = CachedSigLip(args.criteria, cache, extract=True)
        for i, (s, f, path, _) in enumerate(photos, 1):
            if (s, f, "done") in cache:
                continue
            image = load_image(path)
            cache[("size", s, f)] = image.size
            tracked = Tracked((s, f), image)
            engine.encode(tracked)
            engine.encode(measure.crop(tracked, [0, 0, 1, 0.3]))  # the weather crop, whatever the masks decide later
            cache[(s, f, "done")] = True
            if i % 100 == 0:
                print(i, flush=True)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_bytes(pickle.dumps(cache))
        return
    engine = CachedSigLip(args.criteria, cache)
    rows = predict(engine, photos, cache)
    names = measure.criteria_order(args.criteria)
    full, expected = report(rows, photos, names, DEV, "DEV (2+3+4)")
    for n in args.confusion:
        confusion(full, expected, n)
    if args.test:
        report(rows, photos, names, TEST, "TEST A95 (held-out)")


if __name__ == "__main__":
    main()
