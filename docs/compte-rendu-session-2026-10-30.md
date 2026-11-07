# Compte rendu de session : nouveaux critères et dossier 4

**Date :** 30 octobre 2026
**Projet :** `D:\WebstormProjects\sandbox` (dépôt `NicolasGAUD/sandbox`)
**Branche :** `feature/photo-upload-app`

## 1. Résumé

- Deux exports partiels des corrections du dossier 4 pris en compte : `expected_4.json` passe de 1 537 à 3 646 photos.
- Deux séries de changements sur les critères : types, catégories, état, et nouveau champ « Présence d'un personnage ».
- Dans la page de correction, toutes les listes acceptent une nouvelle valeur, et certaines valeurs dépendent du type.
- Sondes réentraînées et CLIP relancé deux fois sur tout le dossier 4. `results_4/review.html` est à jour : 815 photos à revoir.
- Rien n'a été commité ce jour-là. Le travail est commité et poussé le 31 octobre (`364e40f`, `d8d473b`).

## 2. Première série de changements

Faite à partir du premier export partiel (2 805 photos).

| Élément | Changement |
|---|---|
| État | Plus demandé pour Rue et Animal |
| Catégories d'intérieur et d'extérieur | Plus demandées pour Street-art et Église |
| Types | Bâtiment devient Architecture. Mur et Sculpture sont supprimés. Cimetière et Art-Plastiques sont ajoutés. Moulin existait déjà. |
| Art-Plastiques | Propose Sculpture, Photo, Collage et Peinture, en intérieur comme en extérieur |
| Catégorie d'intérieur | Ajout de Couloir |
| Présence d'un personnage | Nouveau champ : Oui, de face / Oui, de dos / Non / Indéterminé. La carte passe en rouge clair pour les deux « Oui ». |
| Listes | « + Nouvelle valeur… » dans toutes les listes |

La règle « mur + graffitis = street-art » disparaît : Street-art est maintenant une vraie option de CLIP.

## 3. Deuxième série de changements

Faite à partir du second export partiel.

| Élément | Changement |
|---|---|
| État | Plus demandé non plus pour Street-art et Macro |
| Présence d'un personnage | Plus demandée pour Macro, Street-art et Graphisme |
| Catégorie d'extérieur | Plus demandée pour Paysage |
| Porte et Fenêtre | Regroupées en une seule catégorie, « Porte / fenêtre », en intérieur comme en extérieur |
| Rue | Gardée dans les deux catégories, « Street » retiré car il faisait doublon |
| Photos au type « — » | 15 photos à supprimer (voir la partie 6) |

## 4. Nouveautés techniques

| Élément | Rôle |
|---|---|
| `values_if` (`criteria.json`) | Remplace les valeurs d'une liste selon une autre réponse. Sert pour Art-Plastiques. Ces valeurs ne sont pas évaluées par CLIP. |
| `manual_values` (`criteria.json`) | Valeurs proposées sur la page seulement. CLIP ne les évalue pas. Sert pour Rue. |
| `--no-html` (`test_clip.py`) | Écrit seulement `results.csv`, sans la page de résultats |

Les scripts se lancent avec `.venv\Scripts\python.exe` : le Python du système n'a pas les dépendances.

## 5. Migration des réponses

`expected.json`, `expected_2.json`, `expected_3.json`, `expected_4.json` et `results_4/results.csv` ont été migrés. Chiffres du dossier 4 :

| Première migration (2 805 photos) | Photos |
|---|---|
| Bâtiment → Architecture | 97 |
| Mur retiré : photo de nouveau « à revoir » | 14 |
| Sculpture → Art-Plastiques + catégorie Sculpture | 1 |
| État effacé (Rue, Animal) | 100 |
| Catégories effacées (Street-art, Église) | 53 |

| Deuxième migration (3 661 photos) | Photos |
|---|---|
| État effacé (Street-art, Macro) | 255 |
| Personnage effacé (Macro, Street-art, Graphisme) | 680 |
| Porte et Fenêtre → Porte / fenêtre | 44 |
| Catégorie d'extérieur effacée sur les paysages | 12 |
| « Rue » et « Street » retirés des catégories d'extérieur | 3 |

- **Personnage :** « Non » a été mis partout par défaut lors de la première migration, pour éviter de tout revalider. Une photo déjà validée où quelqu'un apparaît peut donc être fausse.
- **Trois valeurs perdues :** les 3 réponses « Rue » et « Street » ont été effacées sans sauvegarde, par erreur de Claude. La recherche dans le navigateur n'a rien donné. Ces photos restent sans catégorie d'extérieur, ce qui a été accepté.
- **Photos sans type :** 9 photos de l'export sont d'anciens Mur pas encore revus. Elles restent à revoir.

## 6. Photos au type « — »

Les 15 photos concernées sont retirées de `expected_4.json`, de `results_4/results.csv` et de la page. Les permissions ont refusé la suppression de leurs images à Claude. Elles ont été effacées à la main le 31 octobre : `D:\_Urbex\_tmpEntrainementMdl_4` contient maintenant 4 450 fichiers, et aucune de ces 15 images n'y figure.

## 7. Résultats de CLIP

Dernière analyse de la journée : 4 450 photos, dont 3 646 avec une réponse et 815 à revoir.

| Critère | Validation croisée |
|---|---|
| Type | 89,3 % |
| Catégorie d'intérieur | 87,8 % |
| Météo | 86,0 % |

| Valeur | Photos proposées par CLIP |
|---|---|
| Porte / fenêtre | 23 |
| Art-Plastiques | 14 |
| Moulin | 8 |
| Cimetière | 0, faute d'exemple |
| Rue | 0, valeur à choisir à la main |

**Personnage :** ce champ repose uniquement sur les phrases de `criteria.json`, sans apprentissage, et sa fiabilité n'a pas été mesurée. CLIP voit quelqu'un sur 181 photos validées et sur 25 photos jamais vues. La plupart des 181 portent le « Non » mis par défaut.

## 8. Vérifications

- Le script de la page a été testé dans Node avec un faux navigateur : listes, champs masqués, carte rouge, nouvelles valeurs et export.
- La première version de la page n'a pas été ouverte dans un vrai navigateur par Claude. Les exports ont ensuite été faits depuis le navigateur.
- CLIP a tourné sur le processeur : environ 35 minutes pour le dossier 4.

## 9. Serveurs

Les deux serveurs ont été lancés dans l'après-midi. L'adresse IP du PC était **192.168.0.109** : `http://192.168.0.109:4200/` (développement) ou `http://192.168.0.109:8000/` (version compilée) depuis le téléphone.

Le serveur Python ne lit `criteria.json` et les sondes qu'au démarrage : il faut le relancer pour que l'application prenne en compte ces changements.

## 10. Fichiers modifiés

| Fichier | Changement |
|---|---|
| `criteria.json` | Nouveaux types, catégories, conditions, champ `person`, `values_if`, `manual_values`. Règle du mur retirée. |
| `labels.json` | Libellés français et anglais des nouvelles valeurs |
| `review_page.py` | « + Nouvelle valeur… » partout, listes conditionnelles, carte rouge |
| `test_clip.py` | Option `--no-html` |
| `expected.json`, `expected_2.json`, `expected_3.json`, `expected_4.json` | Migrés, avec les deux exports pour le dossier 4 |
| `probes.pt` | Sondes réentraînées sur les dossiers 2, 3 et 4 |

## 11. Reste à faire

1. Reprendre la correction du dossier 4 dans `results_4/review.html` : les 815 photos à revoir, dont les 181 où CLIP voit quelqu'un (filtre « Seulement les désaccords avec CLIP »).
2. Ajouter des exemples de Cimetière : CLIP ne le propose jamais.
3. Mesurer la fiabilité du champ Personnage.
4. Décider du sort de `results_4/results.html` : c'est l'ancienne page du 26 octobre, avec les anciens critères.
5. Relancer le serveur Python s'il tourne encore.
6. Décider de la fusion de `feature/photo-upload-app` dans `main`.
