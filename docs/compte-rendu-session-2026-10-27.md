# Compte rendu de session : EXIF, texte alternatif et thèmes

**Date :** 27 octobre 2026
**Projet :** `D:\WebstormProjects\sandbox` (dépôt `NicolasGAUD/sandbox`)
**Branche :** `feature/exif-theme-ui`, créée depuis `feature/photo-upload-app` et fusionnée dedans en fin de session

## 1. Résumé

- Les photos validées sont nommées par un timestamp en millisecondes : celui de la date EXIF, sinon celui de l'envoi.
- La carte affiche la date de prise de vue avant le type, ainsi que l'appareil, la vitesse, l'ouverture, la focale et l'ISO sous le nom de la photo.
- Chaque image a un texte alternatif construit à partir des réponses.
- Une photo floue a une carte orange clair et un badge « Floue ».
- Un bouton permet de passer du thème clair au thème sombre.
- Le CSS reprend l'identité de l'ancienne application, `D:\WebstormProjects\myurbex_angular`.
- Test réussi sur le téléphone, puis commit et push.
- La page de correction affiche elle aussi la date, les EXIF et un texte alternatif.
- Défaut de l'export de la page de correction corrigé : il perdait les photos pas encore revalidées.
- 939 photos du dossier 4 sont des doublons des dossiers 2 et 3. Elles sont listées dans `duplicates_4.json`, et une option `--exclude` permet de les écarter.
- Les listes du type, du type de véhicule et des deux catégories sont triées par ordre alphabétique, dans l'application et dans la page de correction.
- En fin de journée, sur les cartes : date sans l'heure, texte alternatif au-dessus du nom de la photo (à la place du nom une fois la photo validée) et mention « Pas d'EXIF ».

## 2. Nom de la photo (`server.py`)

| Cas | Nom du fichier |
|---|---|
| Date EXIF présente (`DateTimeOriginal`, sinon `DateTime`) | Timestamp de la prise de vue, par exemple `1726057599000.jpg` pour le 11 septembre 2024 à 14 h 26 min 39 s |
| Pas de date EXIF | Timestamp de l'envoi |
| Deux photos dans la même seconde | `1726057599000 (2).jpg`, sans écrasement |

- Le fuseau horaire vient de `OffsetTimeOriginal` quand l'appareil l'a écrit. Sinon, la date est lue comme une heure locale du PC.
- Le nom d'origine n'est plus jamais gardé. Avant, il servait quand la date manquait.
- Nouvelles fonctions : `file_name` dans `server.py`, et `read_exif`, `shot_date`, `camera_name`, `positive` dans `photo_exif.py` (voir la section 6). Elles remplacent `shot_name`.
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

## 6. Page de correction (`review_page.py`)

### Date, EXIF et texte alternatif

- Chaque carte commence par une ligne « Date », avec « Date inconnue » sans date EXIF.
- Sous le nom de la photo, une ligne donne l'appareil et les réglages.
- L'image a un texte alternatif construit à partir des réponses, comme dans l'application. Il change avec les listes et sert aussi dans la vue agrandie.
- La lecture des EXIF est passée dans un module partagé, `photo_exif.py`, utilisé par `server.py` et `review_page.py`.
- Sur les 4 465 photos du dossier 4, 4 455 ont une date et 4 440 un appareil. La génération de la page prend 8 secondes, sans relancer CLIP.
- La version de la page n'a pas changé : la progression enregistrée dans le navigateur est conservée.

### Défaut de l'export

Un export partiel de `expected_4.json` contenait **223 photos de moins** que la version commitée : 1 314 contre 1 537. C'étaient toutes des photos « à revoir » depuis la migration du 26 octobre, parmi les 235 qui avaient perdu leur type (anciens `detail`) ou leur météo (crépuscule).

- **Cause :** l'export ne gardait que les photos validées dans la page. Une photo pas encore revalidée disparaissait du fichier, avec ses réponses déjà connues.
- **Rattrapage :** l'export partiel a été supprimé. `expected_4.json` est revenu identique à la version commitée, avec les 1 537 photos.
- **Correction :** une photo du fichier de réponses qui n'a pas été revalidée est exportée telle qu'elle était. À l'import, une photo n'est marquée « vérifiée » que si elle a une réponse pour tous les critères. Avant, toutes les photos importées l'étaient.
- **Test :** le script de la page a tourné dans Node avec un faux navigateur, en validant une page de 50 photos. L'export contient les 1 537 photos, contre 1 352 avant le correctif. Les 185 photos incomplètes restantes sont exportées sans changement et restent « à revoir » après réimport.

## 7. Doublons entre les dossiers

Les 6 359 images des dossiers 2, 3 et 4 ont été comparées de deux façons.

| Doublons | Fichiers identiques | Même prise de vue (date EXIF et appareil) |
|---|---|---|
| Entre les dossiers 2 et 4 | 0 | 526 |
| Entre les dossiers 3 et 4 | 0 | 406 |
| Entre les dossiers 2 et 3 | 48 | 48 |
| À l'intérieur du dossier 2 | 23 | 3 |
| À l'intérieur du dossier 4 | 26 | 43 |
| **Copies en trop** | **97** | **1 055** |

- **Dossier 4 :** 939 de ses 4 465 photos existent aussi dans le dossier 2 ou 3. Ce chiffre est proche des 925 doublons notés le 26 octobre. Aucune n'est identique octet pour octet : elles ont été réexportées.
- **Faux doublons possibles :** les 43 groupes à l'intérieur du dossier 4 sont sans doute des rafales ou du bracketing HDR pris dans la même seconde. Ils ne sont pas comptés comme doublons.
- **Photos non comptées :** une photo sans date EXIF ne peut pas être repérée par cette méthode. C'est le cas d'une dizaine de photos du dossier 4.

### `duplicates_4.json` et l'option `--exclude`

`duplicates_4.json` donne, pour chacune des 939 photos, ses copies dans les autres dossiers :

```json
"DSC00017-HDR.jpg": ["3/Chapelle_Trescouet/DSC00017-HDR.jpg"],
```

920 d'entre elles ont une réponse validée dans `expected_4.json`, et 19 n'ont jamais été vues. Sans les doublons et sans les photos validées, il reste **2 909 photos jamais vues**.

| Script | Commande | Effet sur le dossier 4 |
|---|---|---|
| `test_clip.py` | `--exclude duplicates_4.json` | 4 465 photos trouvées, 939 écartées, 3 526 analysées |
| `train_probes.py` | `--exclude D:\_Urbex\_tmpEntrainementMdl_4 duplicates_4.json` | 617 des 1 537 réponses gardées |

- `train_probes.py` demande le dossier en plus du fichier : une photo du dossier 2 qui porterait le même nom n'est pas écartée par erreur. L'option peut être répétée.
- Le filtrage a été vérifié sans relancer CLIP.

## 8. Ordre des listes déroulantes

Un critère marqué `"sorted": true` dans `criteria.json` a ses valeurs triées par ordre alphabétique de leur libellé. Le tri suit la langue choisie, accents compris : « Église » se range parmi les E. « Indéterminé » reste en fin de liste, avec « — » tout en dernier dans la page de correction. Les valeurs saisies librement sont triées avec les autres.

| Liste | Ordre |
|---|---|
| Type | Alphabétique : Animal, Bâtiment, Bunker… Usine, Véhicule, Indéterminé |
| Type de véhicule | Alphabétique : Avion, Bateau, Bus, Camion… Vélo, Voiture, Indéterminé |
| Catégorie d'intérieur | Alphabétique : Bibliothèque, Délabrement, Escalier, Pièce, Sanitaires, Indéterminé |
| Catégorie d'extérieur | Alphabétique, pour les valeurs qui seront ajoutées |
| État | Très bon état, Bon état, Dégradé, Ruine |
| Moment | Jour, Crépuscule, Nuit |
| Météo | Ensoleillé, Peu nuageux, Mitigé, Nuageux, Mauvais temps |
| Flou | Oui, Non, Indéterminé |

- Le choix s'est fait en deux temps. Le premier essai triait toutes les listes, mais la météo perdait son ordre logique, du plus beau au plus mauvais temps. Seules les listes de types et de catégories sont restées triées.
- Le serveur transmet l'indicateur à l'application (`GET /api/config`), et la page de correction le lit aussi.
- Le serveur Python ne lit `criteria.json` qu'au démarrage : il faut le relancer après un changement.
- `results_4/review.html` est régénéré. La progression enregistrée dans le navigateur est conservée.

## 9. Date, texte alternatif et « Pas d'EXIF » sur les cartes

Dernière demande de la journée, faite sur `feature/photo-upload-app` après la fusion. Elle concerne l'application (pages 2 et 3) et la page de correction.

| Élément | Avant | Après |
|---|---|---|
| Date | « 11 septembre 2024 à 14:26 » | « 11 septembre 2024 », sans l'heure |
| Texte alternatif | Seulement dans l'attribut `alt` de l'image | Écrit en gras au-dessus du nom de la photo |
| Page 3 (photo validée) | Nom du fichier enregistré, par exemple `1726057599000.jpg` | Texte alternatif à la place du nom |
| Photo sans EXIF | Pas de ligne sous le nom | « Pas d'EXIF » / « No EXIF » sous le nom |

- **Texte alternatif :** il suit les réponses, comme celui de l'image. Dans la page de correction, il change dès qu'une liste est modifiée.
- **« Pas d'EXIF » :** la mention apparaît quand la photo n'a ni date ni réglages. Une photo qui a une date mais aucun réglage n'a toujours pas de ligne sous le nom. Le libellé est dans `labels.json` (`ui.no_exif`). Dans le dossier 4, 10 photos sur 4 465 sont dans ce cas.
- **Vérification :** l'application compile sans erreur. Le script de `results_4/review.html`, régénéré, passe le contrôle de syntaxe de Node. La progression enregistrée dans le navigateur est conservée.
- Les serveurs ont été relancés pour un test sur le téléphone.

## 10. Fichiers modifiés

| Fichier | Changement |
|---|---|
| `server.py` | Nom en millisecondes, objet `exif` dans la réponse |
| `photo_exif.py` | Nouveau : lecture des EXIF, partagée par le serveur et la page de correction |
| `review_page.py` | Date, EXIF et texte alternatif sur les cartes. Export et import corrigés. Listes triées. Date sans l'heure, texte alternatif au-dessus du nom, « Pas d'EXIF ». |
| `criteria.json` | Indicateur `"sorted": true` sur le type, le type de véhicule et les deux catégories |
| `test_clip.py`, `train_probes.py` | Option `--exclude` |
| `duplicates_4.json` | Nouveau : les 939 doublons du dossier 4 |
| `labels.json` | Libellés de l'interface (dont « Pas d'EXIF ») et section `alt` |
| `app/src/app/analysis.service.ts` | Date (sans l'heure), ligne EXIF ou « Pas d'EXIF », texte alternatif, flou, thème, tri des listes |
| `app/src/app/app.ts` | Bouton de thème |
| `app/src/app/review.page.ts`, `summary.page.ts`, `upload.page.ts` | Date, EXIF, badge, `alt`. Texte alternatif au-dessus du nom (page 2) ou à sa place (page 3). |
| `app/src/index.html` | Thème appliqué avant l'affichage |
| `app/src/styles.css` | Charte myurbex, deux thèmes, carte floue, ligne du texte alternatif |
| `docs/copie-photo-serveur.md` | Nouveau nommage. Les numéros de lignes sont remplacés par des noms de fonctions. |

## 11. Serveurs

L'adresse IP du PC était **192.168.0.115** dans la journée, puis **192.168.1.167** en soirée : `http://192.168.1.167:4200/` (développement) ou `http://192.168.1.167:8000/` (version compilée) depuis le téléphone. Elle change souvent : la vérifier avec `ipconfig`.

À chacun des cinq arrêts de la journée, `ng serve` a continué d'occuper le port 4200 après l'arrêt de `npm start`. Il a fallu chaque fois arrêter son processus à la main (voir le compte rendu du 26 octobre).

## 12. Historique git

| Commit | Contenu |
|---|---|
| `3029107` | EXIF, texte alternatif, cartes floues et thème clair / sombre |
| `6b388d3` | Première version de ce compte rendu |
| `4b8a1b5` | Date, EXIF et texte alternatif dans la page de correction, module `photo_exif.py` |
| `550031d` | Correction de l'export et de l'import de la page de correction |
| `aa324bd` | Option `--exclude` et `duplicates_4.json` |
| `74f0cd8` | Compte rendu complété |
| `4d1957c` | Listes du type, du type de véhicule et des catégories triées |
| `282764c` | Tri des listes ajouté à ce compte rendu |

### Fusion dans `feature/photo-upload-app`

| Commit | Contenu |
|---|---|
| `9cd4ee1` | Pull request #1 fusionnée sur GitHub : les deux premiers commits (`3029107`, `6b388d3`) |
| `6943c82` | Fusion locale des six commits suivants, de `4b8a1b5` à `282764c`, sans conflit |
| `6026303` | Fusion ajoutée à ce compte rendu |

La branche `feature/exif-theme-ui` est entièrement fusionnée dans `feature/photo-upload-app`. Elle a été supprimée, en local et sur GitHub.

### Après la fusion, sur `feature/photo-upload-app`

| Commit | Contenu |
|---|---|
| `640183a` | Date sans l'heure, texte alternatif au-dessus du nom, « Pas d'EXIF » |

## 13. Suites possibles

1. Reprendre la correction du dossier 4 dans `results_4/review.html` : les 235 photos à revoir, puis les 2 928 jamais vues. L'export peut maintenant être fait à tout moment.
2. Mesurer un score honnête. Retirer les doublons ne suffit pas : il faut aussi que les sondes ne soient pas entraînées sur les photos évaluées. Il y a deux solutions : `train_probes.py --evaluate`, qui fait une validation croisée, ou une évaluation sur les seules photos jamais vues, une fois corrigées.
3. Contrôler l'accessibilité à la main : parcours au clavier, VoiceOver ou TalkBack, zoom à 200 %. Aucune page n'est déclarée conforme RGAA.
4. Décider de la fusion de `feature/photo-upload-app` dans `main`.
