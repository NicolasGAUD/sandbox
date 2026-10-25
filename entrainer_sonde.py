"""Apprend des « sondes » : une petite couche linéaire par critère, posée sur l'empreinte CLIP de l'image.

Chaque sonde part des phrases de criteres.json (le classement « zero-shot ») et ne s'en écarte
que là où les réponses attendues le justifient : une catégorie sans exemple reste reconnue par sa phrase.
Une réponse attendue « indetermine » devient une catégorie apprise à part entière.

Usage :
    python entrainer_sonde.py DOSSIER_PHOTOS [--attendus attendus_2.json] [--evaluer]

--evaluer mesure en validation croisée (chaque photo jugée par une sonde qui ne l'a pas vue)
au lieu d'enregistrer les sondes dans sondes.pt.
"""

import argparse
import json
from pathlib import Path

import torch
from PIL import Image, ImageOps
from transformers import CLIPModel, CLIPProcessor

from test_clip import INDETERMINE, combiner, doubler_phrases, encoder_image, encoder_phrases

PLIS = 5
REGULARISATIONS = [0.01, 0.1, 1.0]  # force du rappel vers les phrases, choisie par validation croisée


def empreintes(modele, processeur, dossier, fichiers, cache, recadrage=None):
    """Empreintes CLIP des images (ou d'une zone, comme dans test_clip.py), mises en cache."""
    deja = torch.load(cache) if cache.exists() else {}
    manquants = [f for f in fichiers if f not in deja]
    for i, f in enumerate(manquants, 1):
        image = ImageOps.exif_transpose(Image.open(dossier / f)).convert("RGB")
        if recadrage:
            g, h, d, b = recadrage
            image = image.crop((int(g * image.width), int(h * image.height),
                                int(d * image.width), int(b * image.height)))
        deja[f] = encoder_image(modele, processeur, image, "cpu")[0]
        if i % 50 == 0:
            print(f"  empreintes : {i}/{len(manquants)}")
    if manquants:
        cache.parent.mkdir(parents=True, exist_ok=True)
        torch.save(deja, cache)
    return torch.stack([deja[f] for f in fichiers])


def entrainer(X, y, W0, echelle, lam):
    """Régression logistique dont les poids sont rappelés vers W0 (les phrases) avec la force lam."""
    W = W0.clone().requires_grad_(True)
    b = torch.zeros(W0.shape[1], requires_grad=True)
    opt = torch.optim.LBFGS([W, b], max_iter=300, line_search_fn="strong_wolfe")

    def perte():
        opt.zero_grad()
        p = torch.nn.functional.cross_entropy(echelle * X @ W + b, y) + lam * ((W - W0) ** 2).sum()
        p.backward()
        return p

    opt.step(perte)
    return W.detach(), b.detach()


def main():
    parser = argparse.ArgumentParser(description="Apprend les sondes linéaires des critères marqués « sonde ».")
    parser.add_argument("dossier", type=Path)
    parser.add_argument("--attendus", type=Path, default=Path(__file__).with_name("attendus_2.json"))
    parser.add_argument("--criteres", type=Path, default=Path(__file__).with_name("criteres.json"))
    parser.add_argument("--sortie", type=Path, default=Path(__file__).with_name("sondes.pt"))
    parser.add_argument("--modele", default="openai/clip-vit-base-patch16")
    parser.add_argument("--evaluer", action="store_true")
    args = parser.parse_args()

    with open(args.criteres, encoding="utf-8") as f:
        criteres = [c for c in json.load(f)["choix"] if c.get("sonde")]
    with open(args.attendus, encoding="utf-8") as f:
        attendus = json.load(f)

    modele = CLIPModel.from_pretrained(args.modele).eval()
    processeur = CLIPProcessor.from_pretrained(args.modele)
    echelle = modele.logit_scale.exp().item()
    fichiers = sorted(attendus)
    sondes = {}
    for c in criteres:
        zone = c.get("recadrage")
        suffixe = "" if not zone else "_" + "-".join(str(v) for v in zone)
        cache = Path(__file__).with_name(".cache") / f"empreintes_{args.dossier.name}{suffixe}.pt"
        E = empreintes(modele, processeur, args.dossier, fichiers, cache, zone)

        # Les catégories : celles de criteres.json, plus « indetermine » s'il figure dans les réponses.
        classes = list(c["options"])
        if any(attendus[f].get(c["nom"]) == INDETERMINE for f in fichiers):
            classes.append(INDETERMINE)
        textes = [encoder_phrases(modele, processeur, v, "cpu")[0] for v in c["options"].values()]
        if INDETERMINE in classes:
            textes.append(torch.zeros_like(textes[0]))  # pas de phrase : appris uniquement sur les exemples
        W0 = torch.stack(textes, dim=1)
        if zone and c.get("avec_image_entiere"):
            cache_entiere = Path(__file__).with_name(".cache") / f"empreintes_{args.dossier.name}.pt"
            E = combiner(E, empreintes(modele, processeur, args.dossier, fichiers, cache_entiere))
            W0 = doubler_phrases(W0.T).T.contiguous()  # LBFGS exige des poids contigus

        idx = [i for i, f in enumerate(fichiers) if attendus[f].get(c["nom"]) in classes]
        X = E[idx]
        y = torch.tensor([classes.index(attendus[fichiers[i]][c["nom"]]) for i in idx])
        plis = torch.arange(len(idx)) % PLIS

        def validation_croisee(lam):
            pred = torch.empty_like(y)
            for k in range(PLIS):
                app, val = plis != k, plis == k
                W, b = entrainer(X[app], y[app], W0, echelle, lam)
                pred[val] = (echelle * X[val] @ W + b).argmax(-1)
            return (pred == y).float().mean().item()

        scores = {lam: validation_croisee(lam) for lam in REGULARISATIONS}
        lam = max(scores, key=scores.get)
        zero_shot = ((echelle * X @ W0).argmax(-1) == y).float().mean().item()
        print(f"{c['nom']:20} {len(idx)} exemples · phrases seules {zero_shot:.1%} · sonde "
              + " · ".join(f"λ={l} {s:.1%}" for l, s in scores.items()))

        if not args.evaluer:
            W, b = entrainer(X, y, W0, echelle, lam)
            sondes[c["nom"]] = {"classes": classes, "W": W, "b": b, "lambda": lam}

    if not args.evaluer:
        torch.save(sondes, args.sortie)
        print(f"Sondes enregistrées : {args.sortie} ({', '.join(sondes)})")


if __name__ == "__main__":
    main()
