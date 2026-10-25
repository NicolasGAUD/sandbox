"""Test de reconnaissance CLIP sur un dossier de photos.

Usage :
    python test_clip.py CHEMIN_DU_DOSSIER [--criteres criteres.json] [--sortie resultats]

Produit resultats/resultats.csv et resultats/resultats.html (miniatures + scores).
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

import torch
from PIL import Image, ImageOps
from transformers import CLIPModel, CLIPProcessor

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
INDETERMINE = "indetermine"
TAILLE_MINIATURE = 320


def charger_criteres(chemin):
    with open(chemin, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("oui_non", []), data.get("choix", [])


def normaliser(sortie):
    # transformers >= 5 renvoie un objet dont pooler_output contient l'embedding projeté ;
    # les versions antérieures renvoyaient directement le tenseur.
    emb = sortie if isinstance(sortie, torch.Tensor) else sortie.pooler_output
    return emb / emb.norm(dim=-1, keepdim=True)


@torch.no_grad()
def encoder_textes(modele, processeur, textes, device):
    entrees = processeur(text=textes, return_tensors="pt", padding=True).to(device)
    return normaliser(modele.get_text_features(**entrees))


def encoder_phrases(modele, processeur, phrases, device):
    # Une phrase ou une liste de phrases : on fait la moyenne de leurs embeddings,
    # ce qui rend le critère moins sensible à une formulation particulière.
    if isinstance(phrases, str):
        phrases = [phrases]
    emb = encoder_textes(modele, processeur, phrases, device).mean(dim=0, keepdim=True)
    return emb / emb.norm(dim=-1, keepdim=True)


@torch.no_grad()
def encoder_image(modele, processeur, image, device):
    entrees = processeur(images=image, return_tensors="pt").to(device)
    return normaliser(modele.get_image_features(**entrees))


def miniature_base64(image):
    mini = image.copy()
    mini.thumbnail((TAILLE_MINIATURE, TAILLE_MINIATURE))
    tampon = io.BytesIO()
    mini.save(tampon, format="JPEG", quality=80)
    return base64.b64encode(tampon.getvalue()).decode("ascii")


def couleur(score):
    # rouge (0) -> vert (1)
    return f"hsl({int(score * 120)}, 70%, 40%)"


def combiner(emb_zone, emb_image):
    # Zone recadrée + image entière, mises bout à bout et renormalisées (option « avec_image_entiere »).
    emb = torch.cat([emb_zone, emb_image], dim=-1)
    return emb / emb.norm(dim=-1, keepdim=True)


def doubler_phrases(emb_phrases):
    # Phrases face à combiner() : le score obtenu est la moyenne de ceux de la zone et de l'image entière.
    return torch.cat([emb_phrases, emb_phrases], dim=-1) / 2 ** 0.5


def masque(critere, predits):
    # « sauf »: {"type_lieu": ["pont", ...]} masque le critère quand un résultat déjà calculé y figure.
    return any(predits.get(nom) in valeurs for nom, valeurs in critere.get("sauf", {}).items())


def prediction(ligne, nom):
    res = ligne["choix"].get(nom) if nom in ligne["choix"] else ligne["scores"].get(nom)
    return None if res is None else res[0]


def marque_verif(ligne, nom):
    # Classe CSS et mention de la valeur attendue quand la photo figure dans attendus.json.
    if nom not in ligne["verif"]:
        return "", ""
    attendu, ok = ligne["verif"][nom]
    if ok:
        return ' class="ok"', ""
    return ' class="faux"', f' <small>(attendu : {html.escape(attendu or "—")})</small>'


def ecrire_html(chemin, lignes, oui_non, choix, infos):
    cartes = []
    for ligne in lignes:
        items = []
        for c in choix:
            classe, attendu = marque_verif(ligne, c["nom"])
            if ligne["choix"][c["nom"]] is None:
                items.append(f'<li{classe}><span>{html.escape(c["nom"])}{attendu}</span><b>—</b></li>')
                continue
            gagnant, p = ligne["choix"][c["nom"]]
            detail = " · ".join(
                f"{html.escape(k)} {v:.0%}" for k, v in ligne["detail_choix"][c["nom"]].items()
            )
            items.append(
                f'<li{classe} title="{detail}"><span>{html.escape(c["nom"])}{attendu}</span>'
                f"<b>{html.escape(gagnant)} {p:.0%}</b></li>"
            )
        for c in oui_non:
            res = ligne["scores"][c["nom"]]
            classe, attendu = marque_verif(ligne, c["nom"])
            valeur = "—" if res is None else f"{res[0]} {res[1]:.0%}"
            style = "" if res is None else f' style="color:{couleur(res[1])}"'
            items.append(f'<li{classe}><span>{html.escape(c["nom"])}{attendu}</span><b{style}>{valeur}</b></li>')
        cartes.append(
            f'<div class="carte"><img src="data:image/jpeg;base64,{ligne["miniature"]}" alt="" '
            f'data-complete="{html.escape(ligne["uri"])}" title="Cliquer pour agrandir">'
            f'<div class="nom">{html.escape(ligne["fichier"])} '
            f'<small>{ligne["temps_ms"]:.0f} ms</small></div><ul>{"".join(items)}</ul></div>'
        )

    page = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Résultats CLIP</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 16px; background: #f4f4f4; color: #222; }}
  .infos {{ margin-bottom: 16px; }}
  .grille {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }}
  .carte {{ background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px #0002; }}
  .carte img {{ width: 100%; height: 200px; object-fit: cover; display: block; }}
  .nom {{ padding: 6px 10px; font-weight: 600; word-break: break-all; }}
  .nom small {{ font-weight: normal; color: #888; }}
  ul {{ list-style: none; margin: 0; padding: 0 10px 10px; font-size: 14px; }}
  li {{ display: flex; justify-content: space-between; border-top: 1px solid #eee; padding: 3px 0; }}
  li.ok {{ background: #e3f6e3; }}
  li.faux {{ background: #fbe0e0; }}
  .carte img {{ cursor: zoom-in; }}
  #visionneuse {{ position: fixed; inset: 0; background: #000e; display: none;
                 flex-direction: column; align-items: center; justify-content: center; gap: 10px; }}
  #visionneuse.ouverte {{ display: flex; }}
  #visionneuse img {{ max-width: 96vw; max-height: 86vh; object-fit: contain; }}
  #visionneuse button {{ font-size: 16px; padding: 8px 20px; cursor: pointer; }}
  #visionneuse .legende {{ color: #ddd; font-size: 14px; }}
</style></head><body>
<h1>Résultats CLIP</h1>
<p class="infos">{html.escape(infos)}<br>Survolez un choix unique pour voir le détail des scores.
Cliquez sur une image pour l'afficher en entier.</p>
<div class="grille">{"".join(cartes)}</div>
<div id="visionneuse">
  <button id="retour">← Retour</button>
  <img alt="">
  <div class="legende"></div>
</div>
<script>
  const vis = document.getElementById("visionneuse");
  const grande = vis.querySelector("img");
  const legende = vis.querySelector(".legende");
  function fermer() {{ vis.classList.remove("ouverte"); grande.removeAttribute("src"); }}
  document.querySelector(".grille").addEventListener("click", e => {{
    const mini = e.target.closest(".carte img");
    if (!mini) return;
    grande.src = mini.dataset.complete;
    legende.textContent = mini.parentElement.querySelector(".nom").textContent;
    vis.classList.add("ouverte");
  }});
  document.getElementById("retour").addEventListener("click", fermer);
  vis.addEventListener("click", e => {{ if (e.target === vis) fermer(); }});
  document.addEventListener("keydown", e => {{ if (e.key === "Escape") fermer(); }});
</script>
</body></html>"""
    chemin.write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Teste CLIP sur un dossier de photos.")
    parser.add_argument("dossier", type=Path, help="dossier contenant les photos")
    parser.add_argument("--criteres", type=Path, default=Path(__file__).with_name("criteres.json"))
    parser.add_argument("--attendus", type=Path, default=Path(__file__).with_name("attendus.json"),
                        help="réponses attendues par photo, pour mesurer les erreurs")
    parser.add_argument("--sondes", type=Path, default=Path(__file__).with_name("sondes.pt"),
                        help="sondes apprises par entrainer_sonde.py, pour les critères marqués « sonde »")
    parser.add_argument("--sortie", type=Path, default=Path("resultats"))
    parser.add_argument("--modele", default="openai/clip-vit-base-patch16")
    parser.add_argument("--recursif", action="store_true", help="inclure les sous-dossiers")
    args = parser.parse_args()

    motif = "**/*" if args.recursif else "*"
    images = sorted(p for p in args.dossier.glob(motif) if p.suffix.lower() in EXTENSIONS)
    if not images:
        sys.exit(f"Aucune image trouvée dans {args.dossier}")

    oui_non, choix = charger_criteres(args.criteres)
    attendus = {}
    if args.attendus.exists():
        with open(args.attendus, encoding="utf-8") as f:
            attendus = json.load(f)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Chargement de {args.modele} sur {device} (téléchargement au premier lancement)…")
    t0 = time.perf_counter()
    modele = CLIPModel.from_pretrained(args.modele).to(device).eval()
    processeur = CLIPProcessor.from_pretrained(args.modele)
    echelle = modele.logit_scale.exp()
    print(f"Modèle chargé en {time.perf_counter() - t0:.1f} s")
    sondes = {}
    if any(c.get("sonde") for c in choix):
        if not args.sondes.exists():
            sys.exit(f"{args.sondes} introuvable : lancez d'abord entrainer_sonde.py")
        sondes = {nom: s for nom, s in torch.load(args.sondes).items()
                  if any(c["nom"] == nom and c.get("sonde") for c in choix)}
        print(f"Sondes utilisées : {', '.join(sondes)}")

    # Les phrases ne changent pas d'une image à l'autre : on les encode une seule fois.
    emb_oui_non = [
        torch.cat([encoder_phrases(modele, processeur, c[cote], device) for cote in ("oui", "non")])
        for c in oui_non
    ]
    emb_choix = [
        torch.cat([encoder_phrases(modele, processeur, v, device) for v in c["options"].values()])
        for c in choix
    ]
    emb_choix = [doubler_phrases(e) if "recadrage" in c and c.get("avec_image_entiere") else e
                 for c, e in zip(choix, emb_choix)]

    lignes = []
    for i, chemin in enumerate(images, 1):
        try:
            image = ImageOps.exif_transpose(Image.open(chemin)).convert("RGB")
        except Exception as e:
            print(f"[{i}/{len(images)}] {chemin.name} : illisible ({e})")
            continue

        debut = time.perf_counter()
        emb_img = encoder_image(modele, processeur, image, device)
        emb_recadrages = {}  # un même recadrage n'est encodé qu'une fois par image
        # Les choix passent en premier (dans l'ordre du fichier) : les critères suivants
        # peuvent être masqués selon leur résultat, via la clé « sauf ».
        predits = {}
        resultats_choix, detail_choix = {}, {}
        for c, emb in zip(choix, emb_choix):
            if masque(c, predits):
                resultats_choix[c["nom"]], detail_choix[c["nom"]] = None, {}
                continue
            emb_zone = emb_img
            if "recadrage" in c:
                # [gauche, haut, droite, bas] en fractions de l'image, ex. [0, 0, 1, 0.4] pour le ciel.
                cle = tuple(c["recadrage"])
                if cle not in emb_recadrages:
                    g, h, d, b = cle
                    zone = image.crop((int(g * image.width), int(h * image.height),
                                       int(d * image.width), int(b * image.height)))
                    emb_recadrages[cle] = encoder_image(modele, processeur, zone, device)
                emb_zone = emb_recadrages[cle]
                if c.get("avec_image_entiere"):
                    emb_zone = combiner(emb_zone, emb_img)
            if c["nom"] in sondes:
                # Sonde apprise (entrainer_sonde.py) à la place des phrases.
                s = sondes[c["nom"]]
                probas = (echelle * emb_zone @ s["W"] + s["b"]).softmax(dim=-1)[0].tolist()
                detail = dict(zip(s["classes"], probas))
            else:
                probas = (echelle * emb_zone @ emb.T).softmax(dim=-1)[0].tolist()
                detail = dict(zip(c["options"].keys(), probas))
            gagnant = max(detail, key=detail.get)
            score = detail[gagnant]
            # Aucune option assez convaincante : on se rabat sur « defaut », sinon on ne tranche pas.
            if score < c.get("seuil", 0):
                gagnant = c.get("defaut", INDETERMINE)
                score = detail.get(gagnant, score)
            resultats_choix[c["nom"]] = (gagnant, score)
            detail_choix[c["nom"]] = detail
            predits[c["nom"]] = gagnant
        scores = {}
        for c, emb in zip(oui_non, emb_oui_non):
            if masque(c, predits):
                scores[c["nom"]] = None
                continue
            p = (echelle * emb_img @ emb.T).softmax(dim=-1)[0][0].item()
            # Entre les deux bornes d'« incertitude », on ne devine pas.
            bas, haut = c.get("incertitude", [0.5, 0.5])
            valeur = "oui" if p >= haut else "non" if p <= bas else INDETERMINE
            scores[c["nom"]] = (valeur, p)
            predits[c["nom"]] = valeur
        temps_ms = (time.perf_counter() - debut) * 1000

        fichier = chemin.relative_to(args.dossier).as_posix()
        verif = {nom: (val, predits.get(nom) == val) for nom, val in attendus.get(fichier, {}).items()}

        lignes.append({
            "fichier": fichier,
            "uri": chemin.resolve().as_uri(),  # image originale, affichée en grand dans le HTML
            "temps_ms": temps_ms,
            "scores": scores,
            "choix": resultats_choix,
            "detail_choix": detail_choix,
            "verif": verif,
            "miniature": miniature_base64(image),
        })
        print(f"[{i}/{len(images)}] {chemin.name} : {temps_ms:.0f} ms")

    if not lignes:
        sys.exit("Aucune image n'a pu être analysée.")

    args.sortie.mkdir(parents=True, exist_ok=True)

    # CSV en UTF-8 avec BOM et séparateur « ; » pour qu'Excel (français) l'ouvre correctement.
    # Chaque critère occupe deux colonnes : la valeur et son score (pour un oui/non, la probabilité du « oui »).
    entetes = ["fichier", "temps_ms"]
    for c in choix + oui_non:
        entetes += [c["nom"], f'{c["nom"]}_score']
    with open(args.sortie / "resultats.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(entetes)
        for l in lignes:
            ligne = [l["fichier"], f'{l["temps_ms"]:.0f}']
            resultats = [l["choix"][c["nom"]] for c in choix] + [l["scores"][c["nom"]] for c in oui_non]
            for res in resultats:
                ligne += ["", ""] if res is None else [res[0], f"{res[1]:.3f}"]
            w.writerow(ligne)

    # La première image inclut souvent un temps de « chauffe » : on l'exclut de la moyenne si possible.
    temps = [l["temps_ms"] for l in lignes]
    moyenne = sum(temps[1:]) / (len(temps) - 1) if len(temps) > 1 else temps[0]
    infos = (f"{len(lignes)} images · modèle {args.modele} sur {device} · "
             f"{moyenne:.0f} ms/image en moyenne (hors première)")
    verifs = [(l, nom, attendu, ok) for l in lignes for nom, (attendu, ok) in l["verif"].items()]
    if verifs:
        justes = sum(ok for *_, ok in verifs)
        # « indéterminé » répondu à la place d'une vraie valeur : pas une erreur, une absence de réponse.
        sans_reponse = sum(not ok and prediction(l, nom) == INDETERMINE for l, nom, _, ok in verifs)
        infos += (f" · {justes}/{len(verifs)} réponses attendues correctes, "
                  f"{sans_reponse} indéterminées, {len(verifs) - justes - sans_reponse} fausses")
        for l, nom, attendu, ok in verifs:
            if not ok and prediction(l, nom) != INDETERMINE:
                print(f"  ✗ {l['fichier']} {nom} : attendu {attendu or '— (non applicable)'}")
    ecrire_html(args.sortie / "resultats.html", lignes, oui_non, choix, infos)

    print(infos)
    print(f"Résultats : {args.sortie / 'resultats.csv'} et {args.sortie / 'resultats.html'}")


if __name__ == "__main__":
    main()
