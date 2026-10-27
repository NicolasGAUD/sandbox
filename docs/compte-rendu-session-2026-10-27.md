# Compte rendu de session : EXIF, texte alternatif et thèmes

**Date :** 27 octobre 2026
**Projet :** `D:\WebstormProjects\sandbox` (dépôt `NicolasGAUD/sandbox`)
**Branche :** `feature/exif-theme-ui`, créée depuis `feature/photo-upload-app`

## 1. Résumé

- Les photos validées sont nommées par un timestamp en millisecondes : celui de la date EXIF, sinon celui de l'envoi.
- La carte affiche la date de prise de vue avant le type, ainsi que l'appareil, la vitesse, l'ouverture, la focale et l'ISO sous le nom de la photo.
- Chaque image a un texte alternatif construit à partir des réponses.
- Une photo floue a une carte orange clair et un badge « Floue ».
- Un bouton permet de passer du thème clair au thème sombre.
- Le CSS reprend l'identité de l'ancienne application, `D:\WebstormProjects\myurbex_angular`.
- Test réussi sur le téléphone, puis commit et push.

## 2. Nom de la photo (`server.py`)

| Cas | Nom du fichier |
|---|---|
| Date EXIF présente (`DateTimeOriginal`, sinon `DateTime`) | Timestamp de la prise de vue, par exemple `1726057599000.jpg` pour le 11 septembre 2024 à 14 h 26 min 39 s |
| Pas de date EXIF | Timestamp de l'envoi |
| Deux photos dans la même seconde | `1726057599000 (2).jpg`, sans écrasement |

- Le fuseau horaire vient de `OffsetTimeOriginal` quand l'appareil l'a écrit. Sinon, la date est lue comme une heure locale du PC.
- Le nom d'origine n'est plus jamais gardé. Avant, il servait quand la date manquait.
- Nouvelles fonctions : `read_exif`, `shot_date`, `camera_name`, `positive`, `file_name`. Elles remplacent `shot_name`.
- La réponse de `POST /api/analyses` contient un objet `exif` : `taken`, `camera`, `exposure_time`, `f_number`, `focal_length`, `iso`. La date est envoyée telle qu'écrite par l'appareil, sans fuseau, pour être affichée sans décalage.

**Vérification :** sur 7 photos du dossier 4, toutes les valeurs sont lues (exemple : `SONY ILCA-68 · 1/500 s · f/8 · 20 mm · ISO 100`). L'API a été testée avec un faux analyseur à la place de CLIP : nommage, doublon et image sans EXIF.

## 3. Carte de la photo (pages 2 et 3)

- **Date :** une ligne « Date » s'affiche avant « Type », formatée selon la langue (« 11 septembre 2024 à 14:26 » / « September 11, 2024 at 2:26 PM »). Seule une date EXIF est affichée. Sinon, la ligne indique « Date inconnue » / « Unknown date ».
- **EXIF :** sous le nom, seules les valeurs présentes sont affichées. Sans aucune, la ligne n'apparaît pas.
- **Flou :** quand le critère « Flou » vaut « Oui », la carte a un fond orange clair, une bordure orange et un badge « Floue ». Le badge évite que l'information repose sur la seule couleur.

## 4. Texte alternatif des images

Le texte se met à jour à chaque changement de réponse. Exemples : « Image d'un château en ruine sous le soleil », « Image d'une voiture délabrée », « Image of a landscape in bad weather ».

- Il est construit à partir du type (ou du type de véhicule), de l'état, de la météo et du moment (crépuscule, nuit). Un critère masqué n'est pas utilisé.
- Les tournures sont dans une nouvelle section `alt` de `labels.json`. Chaque sujet indique son genre (`f`, `mp`, `fp`, masculin par défaut) pour accorder l'état : « délabré », « délabrée », « délabrés », « délabrées ».
- Pendant l'analyse, l'image affiche « Photo en cours d'analyse ».
- Il n'existe pas de valeur « pluie » : le mauvais temps donne « par mauvais temps ».

## 5. Thèmes et CSS

- **Bouton ☾ / ☀** dans l'en-tête, à côté de FR / EN. Son nom accessible reste « Thème sombre » et `aria-pressed` indique s'il est actif. Les boutons de langue sont regroupés dans un groupe nommé « Langue ».
- **Choix du thème :** au premier lancement, il suit celui du téléphone. Le choix est ensuite gardé dans le navigateur (`clip-theme`). Un petit script dans `index.html` applique le thème avant l'affichage, pour éviter un flash.
- **Charte myurbex :** titres cyan en majuscules, Helvetica, boutons à contour cyan remplis au survol, cartes arrondies. Bootstrap et `custom.css` (plus de 4 000 lignes) ne sont pas repris. Le gras sur tout le texte de l'ancienne application n'est pas repris non plus, pour la lisibilité.
- **Thème sombre :** les gris de myurbex (`#22282f`, `#2f353d`), avec un cyan éclairci (`#2bb3a5`).
- **Thème clair :** le cyan est assombri (`#1b756c`, l'ancien `--cyan-hover`). Le cyan d'origine `#239a8e` ne fait que 3,5:1 sur blanc.
- Toutes les couleurs sont des variables dans `:root`, redéfinies sous `[data-theme="dark"]`.
- Focus visible partout, animation ralentie si le téléphone demande moins de mouvements.

### Contrastes calculés

| Couple | Clair | Sombre |
|---|---|---|
| Texte / carte | 14,9:1 | 11,2:1 |
| Texte secondaire / carte | 9,2:1 | 6,6:1 |
| Cyan / carte | 5,5:1 | 4,8:1 |
| Texte du bouton principal / cyan | 5,5:1 | 7,1:1 |
| Badge « Floue » / carte floue | 6,6:1 | 7,3:1 |
| Bordure des listes / carte | 4,3:1 | 3,9:1 |

Seuils WCAG AA : 4,5:1 pour le texte, 3:1 pour les bordures des composants.

## 6. Fichiers modifiés

| Fichier | Changement |
|---|---|
| `server.py` | Lecture des EXIF, nom en millisecondes, objet `exif` dans la réponse |
| `labels.json` | Libellés de l'interface et section `alt` |
| `app/src/app/analysis.service.ts` | Date, ligne EXIF, texte alternatif, flou, thème |
| `app/src/app/app.ts` | Bouton de thème |
| `app/src/app/review.page.ts`, `summary.page.ts`, `upload.page.ts` | Date, EXIF, badge, `alt` |
| `app/src/index.html` | Thème appliqué avant l'affichage |
| `app/src/styles.css` | Charte myurbex, deux thèmes, carte floue |
| `docs/copie-photo-serveur.md` | Nouveau nommage. Les numéros de lignes sont remplacés par des noms de fonctions. |

## 7. Serveur

L'adresse IP du PC était **192.168.0.115** ce jour : `http://192.168.0.115:8000/` depuis le téléphone. Elle change souvent : la vérifier avec `ipconfig`.

## 8. Historique git

| Commit | Contenu |
|---|---|
| `3029107` | EXIF, texte alternatif, cartes floues et thème clair / sombre |

La branche `feature/exif-theme-ui` est poussée sur GitHub.

## 9. Suites possibles

1. Contrôler l'accessibilité à la main : parcours au clavier, VoiceOver ou TalkBack, zoom à 200 %. Aucune page n'est déclarée conforme RGAA.
2. Donner aussi un texte alternatif aux images de la page de correction (`review.html`), qui ont encore `alt=""`.
3. Fusionner `feature/exif-theme-ui` dans `feature/photo-upload-app`, puis décider de la fusion dans `main`.
4. Reprendre la correction du dossier 4 (voir le compte rendu du 26 octobre).
