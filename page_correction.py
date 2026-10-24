"""Génère une page HTML pour vérifier et corriger les réponses de CLIP, 50 photos par page.

Usage :
    python page_correction.py DOSSIER_PHOTOS [--resultats resultats_2/resultats.csv]
                              [--attendus attendus_2.json] [--sortie resultats_2/correction.html]

La page garde la progression dans le navigateur et exporte un fichier d'attendus
(même format que attendus.json) lisible par test_clip.py --attendus.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

INDETERMINE = "indetermine"
NON_APPLICABLE = "—"  # critère masqué (clé « sauf ») : exporté en null


def valeurs_possibles(criteres):
    """Pour chaque critère, dans l'ordre d'affichage : (nom, liste des valeurs proposées)."""
    liste = []
    for c in criteres.get("choix", []):
        valeurs = list(c["options"])
        if "seuil" in c and "defaut" not in c:
            valeurs.append(INDETERMINE)
        liste.append((c["nom"], valeurs + [NON_APPLICABLE]))
    for c in criteres.get("oui_non", []):
        liste.append((c["nom"], ["oui", "non", NON_APPLICABLE]))
    return liste


def lire_predictions(chemin_csv, criteres):
    choix = {c["nom"] for c in criteres.get("choix", [])}
    photos = []
    with open(chemin_csv, encoding="utf-8-sig") as f:
        for ligne in csv.DictReader(f, delimiter=";"):
            predits, scores = {}, {}
            for nom in choix:
                predits[nom] = ligne[nom] or NON_APPLICABLE
                scores[nom] = float(ligne[f"{nom}_score"]) if ligne[f"{nom}_score"] else None
            for c in criteres.get("oui_non", []):
                brut = ligne[c["nom"]]
                if brut:
                    p = float(brut)
                    predits[c["nom"]], scores[c["nom"]] = ("oui" if p >= 0.5 else "non"), p
                else:
                    predits[c["nom"]], scores[c["nom"]] = NON_APPLICABLE, None
            photos.append({"fichier": ligne["fichier"], "predits": predits, "scores": scores})
    return photos


PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Correction CLIP</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; background: #f4f4f4; color: #222; }
  header { position: sticky; top: 0; z-index: 5; background: #fff; box-shadow: 0 1px 4px #0002;
           padding: 8px 16px; display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
  header .stats { font-size: 14px; color: #555; }
  header .actions { margin-left: auto; display: flex; flex-wrap: wrap; gap: 6px; }
  button, select { font: inherit; }
  button { padding: 5px 12px; cursor: pointer; }
  button.principal { background: #2a7d2a; color: #fff; border: 0; border-radius: 4px; }
  main { padding: 16px; }
  .grille { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
  .carte { background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px #0002;
           border: 3px solid transparent; }
  .carte.verifiee { border-color: #2a7d2a55; }
  .carte img { width: 100%; height: 200px; object-fit: cover; display: block; cursor: zoom-in; background: #ddd; }
  .nom { padding: 6px 10px; font-weight: 600; font-size: 13px; word-break: break-all;
         display: flex; justify-content: space-between; gap: 6px; }
  .nom .etat { font-weight: normal; color: #2a7d2a; white-space: nowrap; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  td { padding: 2px 10px; border-top: 1px solid #eee; }
  td:first-child { color: #555; width: 45%; }
  td select { width: 100%; }
  tr.modifie select { background: #ffe2b8; font-weight: 600; }
  tr.modifie td:first-child::after { content: " ✎"; color: #c06000; }
  tr.a-revoir select { background: #fff3a0; }
  tr.a-revoir td:first-child::after { content: " à revoir"; color: #9a7b00; font-size: 11px; }
  label.filtre { font-size: 14px; cursor: pointer; }
  .score { color: #999; font-size: 11px; }
  nav { display: flex; gap: 8px; align-items: center; justify-content: center; margin: 20px 0; flex-wrap: wrap; }
  #visionneuse { position: fixed; inset: 0; z-index: 10; background: #000e; display: none;
                 flex-direction: column; align-items: center; justify-content: center; gap: 10px; }
  #visionneuse.ouverte { display: flex; }
  #visionneuse img { max-width: 96vw; max-height: 86vh; object-fit: contain; }
  #visionneuse button { font-size: 16px; padding: 8px 20px; }
  #visionneuse .legende { color: #ddd; font-size: 14px; }
</style></head><body>
<header>
  <strong>Correction CLIP</strong>
  <span class="stats" id="stats"></span>
  <label class="filtre"><input type="checkbox" id="filtre"> Seulement les photos à revoir</label>
  <span class="actions">
    <button id="exporter">Exporter __NOM_EXPORT__</button>
    <button id="importer">Importer…</button>
    <input type="file" id="fichier-import" accept=".json" hidden>
  </span>
</header>
<main>
  <nav class="pagination"></nav>
  <div class="grille" id="grille"></div>
  <nav class="pagination"></nav>
  <nav><button class="principal" id="valider">Valider la page et continuer →</button></nav>
</main>
<div id="visionneuse"><button id="retour">← Retour</button><img alt=""><div class="legende"></div></div>
<script>
const DONNEES = __DONNEES__;
const PAR_PAGE = 50, NA = "—";
// La version change avec les critères : une progression enregistrée pour d'anciens critères est ignorée.
const CLE = "correction-clip:" + DONNEES.dossier + ":" + DONNEES.version;
const NOMS = DONNEES.criteres.map(([nom]) => nom);

// etat.corrections[fichier][critere] = valeur choisie ; etat.verifiees[fichier] = true
let etat = { corrections: {}, verifiees: {}, page: 0, filtre: null };
try { Object.assign(etat, JSON.parse(localStorage.getItem(CLE)) || {}); } catch (e) {}
// Les attendus déjà connus servent de point de départ ; une photo n'est vérifiée que si tous ses critères y sont.
for (const [f, vals] of Object.entries(DONNEES.attendus)) {
  if (etat.corrections[f]) continue;
  etat.corrections[f] = {};
  for (const [k, v] of Object.entries(vals)) etat.corrections[f][k] = v === null ? NA : v;
  if (NOMS.every(n => n in vals)) etat.verifiees[f] = true;
}
function sauver() { try { localStorage.setItem(CLE, JSON.stringify(etat)); } catch (e) {} }

const photos = DONNEES.photos;
const valeur = (p, nom) => (etat.corrections[p.fichier] || {})[nom] ?? p.predits[nom];
// Critère à revoir : photo pas encore validée et aucune valeur donnée par l'utilisateur pour ce critère.
const aRevoir = (p, nom) => !etat.verifiees[p.fichier] && !(nom in (etat.corrections[p.fichier] || {}));
const partiellementConnue = p => p.fichier in DONNEES.attendus;
if (etat.filtre === null) etat.filtre = photos.some(p => partiellementConnue(p) && !etat.verifiees[p.fichier]);
// En mode filtre : seulement les photos déjà en partie connues mais pas encore validées.
let liste = [];
function calculerListe() {
  liste = etat.filtre ? photos.filter(p => partiellementConnue(p) && !etat.verifiees[p.fichier]) : photos;
}
const nbPages = () => Math.max(1, Math.ceil(liste.length / PAR_PAGE));

function afficherStats() {
  const nbVerif = photos.filter(p => etat.verifiees[p.fichier]).length;
  let nbModif = 0;
  for (const p of photos) for (const nom of NOMS) if (valeur(p, nom) !== p.predits[nom]) nbModif++;
  const restant = photos.filter(p => partiellementConnue(p) && !etat.verifiees[p.fichier]).length;
  document.getElementById("stats").textContent =
    `Page ${etat.page + 1}/${nbPages()} · ${nbVerif}/${photos.length} photos vérifiées · ` +
    `${restant} à revoir · ${nbModif} corrections`;
}

function afficherPagination() {
  for (const nav of document.querySelectorAll(".pagination")) {
    nav.innerHTML = "";
    for (let i = 0; i < nbPages(); i++) {
      const b = document.createElement("button");
      const tranche = liste.slice(i * PAR_PAGE, (i + 1) * PAR_PAGE);
      const faite = tranche.every(p => etat.verifiees[p.fichier]);
      b.textContent = (i + 1) + (faite ? " ✓" : "");
      b.disabled = i === etat.page;
      b.onclick = () => allerA(i);
      nav.appendChild(b);
    }
  }
}

function carte(p) {
  const div = document.createElement("div");
  div.className = "carte" + (etat.verifiees[p.fichier] ? " verifiee" : "");
  const img = document.createElement("img");
  img.loading = "lazy"; img.src = DONNEES.base + encodeURIComponent(p.fichier).replace(/%2F/g, "/");
  img.alt = p.fichier;
  img.onclick = () => ouvrir(img.src, p.fichier);
  div.appendChild(img);
  const nom = document.createElement("div");
  nom.className = "nom";
  nom.innerHTML = `<span></span><span class="etat">${etat.verifiees[p.fichier] ? "✓ vérifiée" : ""}</span>`;
  nom.firstChild.textContent = p.fichier;
  div.appendChild(nom);
  const table = document.createElement("table");
  for (const [critere, options] of DONNEES.criteres) {
    const tr = document.createElement("tr");
    const td1 = document.createElement("td"), td2 = document.createElement("td");
    const sc = p.scores[critere];
    td1.innerHTML = `${critere} <span class="score">${sc === null ? "" : Math.round(sc * 100) + " %"}</span>`;
    const sel = document.createElement("select");
    for (const o of options) {
      const opt = document.createElement("option");
      opt.value = o; opt.textContent = o + (o === p.predits[critere] ? "  (CLIP)" : "");
      sel.appendChild(opt);
    }
    sel.value = valeur(p, critere);
    const marquer = () => {
      tr.classList.toggle("modifie", sel.value !== p.predits[critere]);
      tr.classList.toggle("a-revoir", aRevoir(p, critere));
    };
    marquer();
    sel.onchange = () => {
      etat.corrections[p.fichier] = etat.corrections[p.fichier] || {};
      etat.corrections[p.fichier][critere] = sel.value;
      marquer(); sauver(); afficherStats();
    };
    td2.appendChild(sel); tr.append(td1, td2); table.appendChild(tr);
  }
  div.appendChild(table);
  return div;
}

function allerA(i) {
  calculerListe();
  etat.page = Math.max(0, Math.min(nbPages() - 1, i)); sauver();
  const grille = document.getElementById("grille");
  grille.innerHTML = "";
  for (const p of liste.slice(etat.page * PAR_PAGE, (etat.page + 1) * PAR_PAGE)) grille.appendChild(carte(p));
  if (!liste.length) grille.textContent = "Plus aucune photo à revoir. Pensez à exporter le fichier.";
  afficherPagination(); afficherStats(); window.scrollTo(0, 0);
}

const filtre = document.getElementById("filtre");
filtre.checked = etat.filtre;
filtre.onchange = () => { etat.filtre = filtre.checked; allerA(0); };

document.getElementById("valider").onclick = () => {
  const page = liste.slice(etat.page * PAR_PAGE, (etat.page + 1) * PAR_PAGE);
  for (const p of page) etat.verifiees[p.fichier] = true;
  sauver();
  // En mode filtre, les photos validées sortent de la liste : la page suivante prend leur place.
  const suivante = etat.filtre ? etat.page : etat.page + 1;
  const derniere = etat.filtre ? liste.length <= page.length : etat.page >= nbPages() - 1;
  allerA(suivante);
  if (derniere) alert("Dernière page validée. Pensez à exporter le fichier.");
};

// Export : toutes les valeurs des photos vérifiées (confirmées ou corrigées) ; « — » devient null.
document.getElementById("exporter").onclick = () => {
  const sortie = {};
  for (const p of photos) {
    if (!etat.verifiees[p.fichier]) continue;
    sortie[p.fichier] = {};
    for (const nom of NOMS) {
      const v = valeur(p, nom);
      sortie[p.fichier][nom] = v === NA ? null : v;
    }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(sortie, null, 2)], { type: "application/json" }));
  a.download = DONNEES.nomExport;
  a.click();
  URL.revokeObjectURL(a.href);
};

// Import : reprend un fichier exporté (les photos qu'il contient sont considérées comme vérifiées).
document.getElementById("importer").onclick = () => document.getElementById("fichier-import").click();
document.getElementById("fichier-import").onchange = async e => {
  const f = e.target.files[0];
  if (!f) return;
  try {
    const donnees = JSON.parse(await f.text());
    for (const [fichier, vals] of Object.entries(donnees)) {
      etat.corrections[fichier] = {};
      for (const [k, v] of Object.entries(vals)) etat.corrections[fichier][k] = v === null ? NA : v;
      etat.verifiees[fichier] = true;
    }
    sauver(); allerA(etat.page);
  } catch (err) { alert("Fichier illisible : " + err.message); }
  e.target.value = "";
};

const vis = document.getElementById("visionneuse"), grande = vis.querySelector("img");
function ouvrir(src, nom) { grande.src = src; vis.querySelector(".legende").textContent = nom; vis.classList.add("ouverte"); }
function fermer() { vis.classList.remove("ouverte"); grande.removeAttribute("src"); }
document.getElementById("retour").onclick = fermer;
vis.onclick = e => { if (e.target === vis) fermer(); };
document.addEventListener("keydown", e => { if (e.key === "Escape") fermer(); });

allerA(etat.page);
</script>
</body></html>
"""


def main():
    parser = argparse.ArgumentParser(description="Page de correction des réponses CLIP.")
    parser.add_argument("dossier", type=Path, help="dossier des photos analysées")
    parser.add_argument("--resultats", type=Path, default=Path("resultats_2/resultats.csv"))
    parser.add_argument("--criteres", type=Path, default=Path(__file__).with_name("criteres.json"))
    parser.add_argument("--attendus", type=Path, default=Path(__file__).with_name("attendus_2.json"))
    parser.add_argument("--sortie", type=Path, default=Path("resultats_2/correction.html"))
    args = parser.parse_args()

    with open(args.criteres, encoding="utf-8") as f:
        criteres = json.load(f)
    attendus = {}
    if args.attendus.exists():
        with open(args.attendus, encoding="utf-8") as f:
            attendus = json.load(f)

    criteres_page = valeurs_possibles(criteres)
    donnees = {
        "dossier": str(args.dossier.resolve()),
        "version": hashlib.sha1(json.dumps(criteres_page).encode()).hexdigest()[:10],
        "base": args.dossier.resolve().as_uri() + "/",
        "nomExport": args.attendus.name,
        "criteres": criteres_page,
        "photos": lire_predictions(args.resultats, criteres),
        "attendus": attendus,
    }
    # « </ » dans le JSON fermerait la balise <script>.
    json_page = json.dumps(donnees, ensure_ascii=False).replace("</", "<\\/")
    page = PAGE.replace("__DONNEES__", json_page).replace("__NOM_EXPORT__", args.attendus.name)
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    args.sortie.write_text(page, encoding="utf-8")
    print(f"{len(donnees['photos'])} photos · page écrite : {args.sortie}")


if __name__ == "__main__":
    main()
