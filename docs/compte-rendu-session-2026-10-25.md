# Compte rendu de session : reconnaissance de photos d'urbex avec CLIP

**Date :** 25 octobre 2026
**Projet :** `D:\WebstormProjects\sandbox` (dépôt `NicolasGAUD/sandbox`)
**Branches :** `main` et `feature/photo-upload-app`

## 1. Objectif

Classer automatiquement des photos d'urbex selon plusieurs critères : type de lieu, intérieur ou extérieur, état, ciel, moment de la journée, météo, etc. Le classement repose sur CLIP, utilisé sans entraînement complet du modèle.

Contraintes fixées pendant la session :

- **Cible mobile :** pas de modèle lourd. Le modèle reste `openai/clip-vit-base-patch16`, et `clip-vit-large-patch14` a été écarté.
- **Ne jamais inventer :** quand aucune catégorie ne correspond, la réponse attendue est « indéterminé ». Tous les seuils de confiance sont à 0.
- **Langue :** le code et les fichiers JSON sont en anglais. L'affichage est en français ou en anglais, au choix, grâce à un bouton FR / EN.

## 2. Méthode

1. **Classement sans exemple (« zero-shot ») :** chaque option d'un critère est décrite par une ou plusieurs phrases en anglais, dans `criteria.json`. CLIP retient l'option dont les phrases ressemblent le plus à l'image.
2. **Sondes linéaires :** pour les critères difficiles, une petite couche linéaire est apprise sur l'empreinte CLIP de l'image, à partir des réponses corrigées à la main. Elle part des phrases et ne s'en écarte que là où les exemples le justifient. Elle est très légère, donc compatible avec un téléphone.
3. **Mesure honnête :** les scores sont mesurés en validation croisée à 5 plis, chaque photo étant jugée par une sonde qui ne l'a jamais vue.
4. **Dépendances entre critères :** `except` masque un critère selon une réponse précédente (par exemple, pas de météo en intérieur). `only_if` ne l'affiche que dans un cas précis (le type de véhicule seulement pour un véhicule).
5. **Règles :** un mur avec des graffitis devient `street_art`.

## 3. Jeux de photos

| Dossier | Contenu | Usage |
|---|---|---|
| `_tmpEntrainementMdl` | 17 photos | Premiers réglages |
| `_tmpEntrainementMdl_2` | 640 photos, toutes corrigées | Apprentissage des sondes |
| `_tmpEntrainementMdl_3` | 1 254 photos dans 153 sous-dossiers, dont 700 corrigées | Test sur des photos jamais vues, puis apprentissage |

## 4. Critères

| Critère | Options | Méthode |
|---|---|---|
| Type de lieu | usine, maison, hôpital, église, château, bureau, bâtiment, mur, street-art, bunker, pont, toit, paysage, véhicule, maison de garde, cabane de vigne, phare, détail, façade, rue | Sonde |
| Type de véhicule (si véhicule) | bateau, avion, voiture, camion, bus, char d'assaut, caravane, vélo | Sonde |
| Intérieur / extérieur | intérieur, extérieur | Phrases |
| Catégorie d'intérieur (si intérieur) | pièces, escaliers, bureau, délabrement, architecture et graphisme, bibliothèque, sanitaires | Sonde |
| État | très bon état, bon état, dégradé, ruine | Phrases |
| Ciel | visible, absent | Sonde |
| Moment | jour, crépuscule, nuit | Sonde |
| Météo (extérieur, de jour, ciel visible) | ensoleillé, peu nuageux, mitigé, nuageux, mauvais temps | Sonde, sur le haut de l'image et l'image entière |
| Végétation, graffitis | oui, non | Phrases, calculés mais masqués |

La météo n'a pas d'option « indéterminé ». Les cinq niveaux ont été définis par la part de ciel bleu : environ 95 %, 75 %, 50 %, moins de 25 % (nuages blancs ou voile), moins de 20 % (nuages sombres et menaçants).

## 5. Résultats

### Premier test honnête sur le dossier 3

Ce test porte sur 700 photos, jugées par des sondes apprises sur le seul dossier 2.

| Critère | Justesse | Erreur principale (attendu → réponse de CLIP) |
|---|---|---|
| Type de lieu | 80,5 % | véhicule → détail (16) |
| Intérieur / extérieur | 97,4 % | intérieur → extérieur (17) |
| Catégorie d'intérieur | 62,1 % | pièces → délabrement (34) |
| État | 84,8 % | ruine → dégradé (66) |
| Ciel | 96,3 % | absent → visible (25) |
| Moment | 99,7 % | crépuscule → jour (2) |
| Météo | 67,6 % | nuageux → mitigé (15) |

### Validation croisée sur les dossiers 2 et 3 réunis

Ce sont les chiffres de référence actuels.

| Critère | Phrases seules | Sonde |
|---|---|---|
| Type de lieu | 56,6 % | 83,0 % |
| Type de véhicule | 93,6 % | 96,8 % |
| Catégorie d'intérieur | 40,1 % | 69,3 % |
| Ciel | 87,1 % | 95,7 % |
| Moment | 89,3 % | 99,0 % |
| Météo | 60,8 % | 72,1 % (89,6 % à un niveau près, mesuré sur le dossier 2) |
| Intérieur / extérieur | 98,1 % | 98,1 % : sonde inutile |
| État | 87,3 % | 84,8 % : sonde moins bonne |

### Pistes testées puis écartées

- **Recadrage automatique sur le ciel pour la météo :** la zone de ciel est détectée par sa couleur, bleue ou claire et sans teinte. Le recadrage cadre bien le ciel sur la photo DSC03077, dont le haut est masqué par des arbres, mais il fait moins bien en moyenne (70,4 % contre 72,1 %). Il reste disponible avec `"crop": "sky"`. DSC03077 est de toute façon correctement classée par les sondes réapprises.
- **Sondes pour l'état et pour intérieur / extérieur :** elles n'améliorent rien par rapport aux phrases.
- **Modèle plus gros :** écarté à cause de la cible mobile.

## 6. Changements demandés pendant la session

- Les types de lieu « indéterminé » mis à tort dans le dossier 3 (172 photos) ont été ignorés, puis recorrigés.
- Nouveau critère « type de véhicule ». Le bateau devient un type de véhicule (39 photos converties).
- Un mur avec des graffitis devient « street-art » (52 réponses converties). Végétation et graffitis sont toujours calculés, mais n'apparaissent plus dans les résultats ni dans les pages.
- L'option « indéterminé » est retirée de la météo.
- Le code et les fichiers JSON sont passés en anglais. Le nouveau fichier `labels.json` donne les libellés français et anglais, affichés selon le bouton FR / EN.
- Les anciennes sauvegardes `attendus*.avant_*.json` et les dossiers `resultats*` ont été supprimés.

## 7. Outils du projet

| Fichier | Rôle |
|---|---|
| `test_clip.py` | Analyse un dossier (`--recursive` pour les sous-dossiers) et produit `results.csv` et `results.html`. Contient la classe `Analyzer`. |
| `train_probes.py` | Apprend les sondes sur un ou plusieurs dossiers (`--data DOSSIER ATTENDUS`, option répétable). `--evaluate` lance la validation croisée. |
| `review_page.py` | Page de correction : 50 photos par page, listes déroulantes, filtre « à revoir », export du fichier d'attendus. |
| `criteria.json` | Critères, phrases, dépendances et règles. |
| `labels.json`, `labels.py` | Libellés français et anglais, et bouton FR / EN. |
| `expected.json`, `expected_2.json`, `expected_3.json` | Réponses corrigées à la main. |
| `probes.pt` | Sondes apprises. |
| `server.py` | API de l'application mobile (FastAPI). |
| `app/` | Application mobile (Angular 22). |

## 8. Application mobile (branche `feature/photo-upload-app`)

1. **Envoi :** l'utilisateur choisit une photo par glisser-déposer, par le bouton « Parcourir… » ou par le bouton « Prendre une photo », qui ouvre l'appareil photo du téléphone.
2. **Analyse et formulaire :** la photo est analysée par le serveur, puis une carte s'affiche avec un formulaire prérempli par CLIP, modifiable par listes déroulantes. Les critères dépendants s'affichent ou se masquent selon les réponses.
3. **Validation :** la photo est copiée dans le dossier de photos, et ses réponses sont ajoutées à `expected.json`, au même format que les autres fichiers d'attendus.
4. **Récapitulatif :** la carte n'est plus modifiable. Les modifications de l'utilisateur sont en vert, la proposition de CLIP est barrée en rouge, avec son pourcentage.

Interface pensée d'abord pour le mobile, avec de grandes zones tactiles, un mode sombre et le bouton FR / EN. Le parcours a été testé sous Chrome à la taille d'un téléphone (390 × 844), sans erreur.

**Lancement :** `.venv/Scripts/python.exe server.py --photos <dossier>`, puis ouvrir `http://<IP du PC>:8000/` depuis le téléphone, sur le même Wi-Fi. Pour l'instant, l'analyse tourne sur le PC, en environ 0,5 seconde par photo.

## 9. Historique git

| Commit | Branche | Contenu |
|---|---|---|
| `fed5d0f` | main | Sondes linéaires, météo à 5 niveaux, catégories d'intérieur |
| `d69e9f5` | main | Code et JSON en anglais, libellés FR/EN, type de véhicule, street-art, dossier 3 |
| `2db188c` | main | Nettoyage du `.gitignore` |
| `eb14771` | feature/photo-upload-app | Application mobile Angular et serveur d'analyse |

Pas encore commités : `criteria.json` (sonde du type de véhicule), `expected_3.json` (corrections en cours) et `probes.pt`.

## 10. Suites possibles

1. Finir de corriger les 554 photos restantes du dossier 3, réapprendre les sondes, puis commiter `criteria.json`, `expected_3.json` et `probes.pt`.
2. Clarifier la frontière entre « pièces », « délabrement » et « architecture et graphisme » : c'est la première source d'erreurs de la catégorie d'intérieur.
3. Ajouter des exemples pour les catégories rares : cabane de vigne, maison de garde, phare, rue, bibliothèque, sanitaires, et certains types de véhicule.
4. Faire tourner CLIP directement sur le téléphone, par exemple avec un export ONNX de l'encodeur d'image et des sondes. C'est la cible finale.
5. Fusionner `feature/photo-upload-app` dans `main` une fois l'application validée sur un vrai téléphone.
