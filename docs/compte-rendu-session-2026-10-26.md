# Compte rendu de session : nouveaux critères et outillage

**Date :** 26 octobre 2026
**Projet :** `D:\WebstormProjects\sandbox` (dépôt `NicolasGAUD/sandbox`)
**Branche :** `feature/photo-upload-app`

## 1. Résumé

- Réglages de Claude Code réparés : `settings.json` était illisible, ce qui désactivait toutes les règles de permission.
- Faille de sécurité de Vite corrigée dans l'application Angular.
- Export partiel des corrections du dossier 4 enregistré.
- Nouveaux critères : flou, catégorie d'extérieur, nouveaux types de lieu et de véhicule, météo au crépuscule. Les catégories `detail`, `office` (intérieur) et `archi_graphism` sont supprimées.
- Fichiers de réponses migrés, sondes réapprises, page de correction du dossier 4 régénérée.
- « Type de lieu » renommé « Type ». La page de correction affiche ou masque les critères selon les réponses.

## 2. Réglages de Claude Code

| Problème | Correction |
|---|---|
| `C:\Users\Nico\.claude\settings.json` : JSON invalide, à cause d'une virgule en trop après le dernier élément des listes `ask` et `deny` | Virgules retirées. Les règles `ask` (installations npm, `git commit`…) et `deny` (`rm`, `del`, `Remove-Item`…) s'appliquent de nouveau. |
| Hook `confirm-npm-install.js` déclaré avec un champ `args`, que Claude Code ne prend pas en charge : `node` était lancé sans le script | Chemin du script intégré dans `command` : `node "C:/Users/Nico/.claude/hooks/confirm-npm-install.js"` |

**Vérification :** un `npm install` dans `app/` a bien affiché la demande de confirmation du hook, « Installation npm détectée : … Confirmer ? ».

## 3. Sécurité de l'application Angular

`npm audit` signalait une faille élevée dans **Vite 8.3.0**, le moteur du serveur de développement (`ng serve`). Elle permettait notamment d'exécuter des scripts depuis un autre site et de lire des fichiers hors du projet. Elle compte ici, parce que `ng serve` écoute sur tout le réseau (`"host": "0.0.0.0"` dans `angular.json`).

- `npm audit fix --force` a été écarté : il aurait rétrogradé `@angular/build` de 22.2.4 (la dernière version) à 22.1.9.
- `@angular/build` 22.2.4 impose Vite 8.3.0. Un champ `"overrides": { "vite": "8.3.5" }` dans `app/package.json` force la version corrigée.
- Résultat : 0 vulnérabilité. `ng build` et `ng serve` fonctionnent.
- **À faire :** retirer l'override dès qu'une version de `@angular/build` utilisera un Vite corrigé.

## 4. Serveurs

| Serveur | Commande | Adresse depuis le téléphone | Contenu |
|---|---|---|---|
| Serveur Python | `start_server.bat` | `http://<IP du PC>:8000/` | Version compilée de l'application (`app\dist`) et API |
| Serveur de développement | `npm start` dans `app/` | `http://<IP du PC>:4200/` | Version de développement, rechargée à chaque modification. Les appels `/api` sont relayés vers le port 8000, qui doit donc tourner aussi. |

L'adresse IP du PC a changé deux fois dans la journée : 192.168.0.112 l'après-midi, puis de nouveau 192.168.1.167 le soir. La vérifier avec `ipconfig` avant chaque test.

Pendant la session, les deux serveurs lancés en arrière-plan ont été coupés par Claude Code, faute de mémoire sur le PC. Le service Angular de WebStorm peut occuper jusqu'à 3 Go.

**`ng serve` survit à l'arrêt de `npm start`** : c'est arrivé deux fois. Seule la fenêtre ou la tâche s'arrête, le processus `node … ng.js serve` continue d'occuper le port 4200, et un nouveau `npm start` échoue avec « Port 4200 is already in use ». Il faut alors retrouver ce processus et l'arrêter :

```powershell
Get-NetTCPConnection -LocalPort 4200 -State Listen | Select-Object OwningProcess
Stop-Process -Id <PID>
```

Le serveur Python, lui, s'arrête normalement.

## 5. Nouveaux critères

Les clés restent en anglais et au singulier. Les libellés français sont dans `labels.json`.

| Critère | Changement |
|---|---|
| Type (anciennement « Type de lieu ») | `detail` supprimé, remplacé par `animal` (Animal), `graphic` (Graphisme), `macro` (Macro) et `sculpture` (Sculpture). Ajout de `farm` (Ferme), `railway` (Rails), `cave` (Grotte), `cellar` (Cave) et `mill` (Moulin). |
| Type de véhicule | Ajout de `tractor` (Tracteur) et `train` (Train). |
| Catégorie d'intérieur | `rooms` → `room` (Pièce), `stairs` → `staircase` (Escalier). `office` supprimé : c'est déjà un type de lieu. `archi_graphism` supprimé. |
| Catégorie d'extérieur | Nouveau critère, en extérieur seulement, **sans valeur pour l'instant**. |
| Météo | Demandée aussi au crépuscule, avec les mêmes valeurs que le jour. Affichée seulement si le ciel est visible. Toujours masquée en intérieur, sur un mur et la nuit. |
| Flou | Nouveau critère oui / non, compté dans les scores. |

Attention aux faux amis : en anglais, une grotte se dit *cave* et une cave à vin *cellar*.

### Page de correction (`review_page.py`)

- **Photos floues :** une photo marquée floue a un fond violet.
- **Saisie libre :** un critère marqué `"free": true` dans `criteria.json` (pour l'instant la catégorie d'extérieur) propose « + Nouvelle valeur… » dans sa liste. La valeur tapée est ensuite proposée sur toutes les photos et part dans l'export. Elle est aussi retrouvée à l'import d'un fichier.
- Un critère sans option n'est pas évalué par CLIP (`test_clip.py`), et l'application mobile ne l'affiche pas.
- **Affichage selon les réponses :** la page applique les règles `except` et `only_if` de `criteria.json` aux réponses en cours, comme le faisait déjà l'application mobile. Avant, elle affichait tous les critères.

| Critère | Affiché seulement si |
|---|---|
| Type de véhicule | Type = Véhicule |
| Catégorie d'intérieur | Intérieur / extérieur = Intérieur |
| Catégorie d'extérieur | Intérieur / extérieur = Extérieur |
| Météo | Ciel = Visible, et ni intérieur, ni mur, ni nuit |
| État | Type différent de Paysage |

Un critère masqué est exporté vide (`null`), même s'il avait une valeur. Un critère qui apparaît sans réponse est marqué « à revoir ». C'est le cas quand CLIP l'avait lui-même masqué, par exemple le type de véhicule quand on choisit « Véhicule ».

Avec la nouvelle règle de météo, 7 photos validées ont une météo alors que leur ciel n'est pas visible (2 dans le dossier 2, 1 dans le dossier 3, 4 dans le dossier 4). Celles du dossier 4 perdront leur météo au prochain export. Celles des dossiers 2 et 3 la gardent dans les fichiers.

## 6. Migration des fichiers de réponses

Fichiers migrés : `expected.json`, `expected_2.json`, `expected_3.json`, `expected_4.json` et `photos/expected.json`.

| Règle | Dossier 2 | Dossier 3 | Dossier 4 |
|---|---|---|---|
| `rooms` → `room` | 9 | 101 | 70 |
| `stairs` → `staircase` | 6 | 22 | 24 |
| `office` (intérieur) → sans catégorie | 6 | 4 | 6 |
| `archi_graphism` → sans catégorie | 22 | 123 | 117 |
| `detail` → type de lieu retiré, à reclasser | 18 | 117 | 187 |
| Crépuscule en extérieur, ciel visible, sans météo → météo à renseigner | 33 | 0 | 48 |

Sur toutes les photos déjà validées, le flou est réglé sur « non » et la catégorie d'extérieur reste vide. Dans `photos/expected.json`, qui contient les photos de l'application, 2 photos `detail` sont aussi à reclasser.

Une photo dont un critère n'a plus de réponse revient dans le filtre « à revoir » de la page de correction.

## 7. Sondes réapprises (dossiers 2, 3 et 4)

| Critère | Exemples | Phrases seules | Sonde |
|---|---|---|---|
| Type de lieu | 3 109 | 55,7 % | 92,9 % |
| Type de véhicule | 223 | 79,8 % | 96,4 % |
| Intérieur / extérieur | 3 431 | 94,9 % | 98,1 % |
| Catégorie d'intérieur | 477 | 45,9 % | 91,4 % |
| Ciel | 3 431 | 87,9 % | 97,6 % |
| Moment | 3 431 | 85,9 % | 99,4 % |
| Météo | 1 980 | 61,8 % | 83,4 % |

**Ces chiffres sont trop optimistes.** Les 925 doublons du dossier 4 sont aussi dans les dossiers 2 et 3 : une photo peut être jugée par une sonde qui a déjà vu sa copie. Ils ne remplacent pas les chiffres de référence du 25 octobre. De plus, les nouveaux types de lieu et de véhicule n'ont encore aucun exemple : ils ne sont reconnus que par leurs phrases.

## 8. Dossier 4 après régénération

Analyse CLIP des 4 465 photos : environ 50 minutes sur le processeur, sans GPU.

- **235 photos validées sont à revoir :** 187 anciens `detail` et 48 photos au crépuscule à qui il manque la météo.
- **2 928 photos** n'ont encore jamais été vues.
- **Flou :** CLIP en voit 427 sur l'ensemble du dossier, dont 103 parmi les photos déjà validées (réglées sur « non »). Le filtre « Seulement les désaccords avec CLIP » permet de les retrouver.
- **Nouveaux types de lieu :** CLIP ne les propose presque jamais (5 photos). Pour les anciens `detail`, il propose surtout « Indéterminé » (60) ou « Mur » (40). Il faudra les classer à la main.
- La progression enregistrée dans le navigateur repart de zéro, parce que les critères ont changé. Les photos déjà validées sont toutes dans l'export.
- `results_4/review - Copie.html` est l'ancienne page : **ne pas exporter depuis celle-ci**, son export écraserait `expected_4.json` avec les anciens critères.

## 9. Historique git

| Commit | Contenu |
|---|---|
| `baed653` | Vite forcé en 8.3.5 |
| `315ebbb` | Export partiel des corrections du dossier 4, tel quel |
| `fb29f95` | Nouveaux critères, migration des réponses, sondes réapprises |
| `5ab45fa` | Première version de ce compte rendu |
| `e37f218` | « Type », critères affichés selon les réponses, météo seulement si le ciel est visible |

Tous ces commits sont poussés sur GitHub.

## 10. Suites possibles

1. Corriger le dossier 4 dans `results_4/review.html` : les 235 photos à revoir, le flou, les nouveaux types de lieu, puis les 2 928 photos jamais vues. Exporter `expected_4.json` dans le dossier du projet.
2. Remplir la catégorie d'extérieur au fil des corrections. Une fois les valeurs stabilisées, les ajouter dans `criteria.json` avec des phrases et des clés anglaises, et leurs libellés dans `labels.json`.
3. Reclasser les 135 anciens `detail` des dossiers 2 et 3. Il faudra d'abord relancer `test_clip.py` sur ces dossiers, parce que `results_2` n'existe plus.
4. Mesurer un score honnête sur les seules photos jamais vues du dossier 4, sans les 925 doublons. Puis réapprendre les sondes.
5. Décider de la fusion de `feature/photo-upload-app` dans `main`.
