# Intégrer l'IA dans MyUrbex et continuer à l'entraîner

**Date :** 31 octobre 2026
**Projets :** `D:\WebstormProjects\sandbox` (entraînement), `D:\_Urbex\myurbex\myurbex-ai` (service IA), `D:\_Urbex\myurbex\myurbex-backend` (back), `D:\_Urbex\myurbex\myurbex-frontend` (front)
**État :** `myurbex-ai` est créé, `sandbox` utilise son code d'analyse, et le cache et les plis sont corrigés. Le back et le front ne sont pas encore modifiés. Rien n'est commité.

## 1. Résumé

Garder l'IA comme un service Python séparé, `myurbex-ai`, appelé uniquement par Spring Boot, et faire remonter les corrections des utilisateurs en base pour réentraîner dans `sandbox`.

Le « modèle » s'y prête bien : CLIP reste figé et seules les sondes sont réentraînées. L'entraînement peut donc continuer sur le PC, et seuls quelques petits fichiers sont à déployer.

## 2. Architecture

```text
Angular ──JWT──> Spring Boot ──réseau interne──> myurbex-ai (FastAPI + CLIP)
                     │                                 ▲
                     ├── MariaDB : suggestions de l'IA │ copie d'une version de modèle
                     │   + réponses validées           │
                     └── IMAGES_DIR : photos           │
                               │ export                │
                               ▼                       │
              PC, sandbox : train_probes.py ───────────┘
```

```text
D:\_Urbex\myurbex\
├── myurbex-backend/
├── myurbex-frontend/
└── myurbex-ai/          dépôt Git séparé, avec son propre .venv
    ├── service.py       routes /v1/analyze, /v1/config, /v1/health
    ├── analyzer.py      code d'analyse, seule copie
    ├── requirements.txt versions figées
    └── models/
        ├── current.txt  version servie
        └── 2026-10-31/  criteria.json, labels.json, probes.pt
```

- **`myurbex-ai` :** c'est le seul projet déployé. Il contient le service, le code d'analyse et les modèles validés.
- **`sandbox` :** il reste le labo d'entraînement, avec `app/`, `review_page.py`, `train_probes.py` et les réponses attendues. `server.py` et l'application téléphone continuent de fonctionner. Il n'entre pas dans MyUrbex.
- **Code partagé :** `sandbox` importe `analyzer.py` avec `pip install -e`. Un modèle se comporte donc en production comme il a été évalué.
- **Sécurité :** le service n'a aucune authentification. Il écoute sur `127.0.0.1` par défaut : le front ne doit jamais l'appeler directement, et il ne doit pas être joignable depuis l'extérieur.

## 3. Intégration

### Service IA

`myurbex-ai/service.py` ne fait que l'analyse et la configuration, sans état :

- `POST /v1/analyze`, qui renvoie aussi la version du modèle ;
- `GET /v1/config` ;
- `GET /v1/health`.

Dans MyUrbex, l'attente de validation et le classement des réponses reviennent à Spring. `server.py` garde ce rôle pour le labo.

### Base de données

Ajouter une migration Flyway après la V4, déjà réservée au nettoyage. Elle crée une table `image_ai` :

| Colonne | Rôle |
|---|---|
| `image_id` | Photo concernée |
| `model_version` | Version du modèle qui a répondu |
| `predicted` (JSON) | Suggestions de l'IA |
| `answers` (JSON) | Réponses validées |
| `status` | État de la validation |
| `validated_by`, `validated_at` | Auteur et date de la validation |

Avec du JSON, ajouter un critère ne demandera pas de nouvelle migration.

### Back

- `POST /api/ai/analyses` relaie la photo vers Python, sans rien stocker.
- `GET /api/ai/config` relaie les critères et les libellés.
- L'envoi réel des photos et des réponses est à créer. **Aucun endpoint d'écriture n'existe encore** : c'est le vrai prérequis, et `PhotoSlots` garde pour l'instant les photos en local.

### Front

Dans le formulaire d'un lieu, l'analyse se lance au choix de la photo. L'utilisateur corrige les suggestions, et tout part à l'enregistrement. Les formulaires se construisent depuis la configuration, sans critère écrit en dur.

## 4. Continuer à entraîner

1. **Exporter :** une route admin génère `expected_myurbex.json` au format des `expected_*.json`. `train_probes.py` accepte des chemins relatifs, donc les `image.name` conviennent tels quels.
2. **Évaluer** dans `sandbox` avant d'enregistrer quoi que ce soit, avec `--evaluate`. La commande ci-dessous est à compléter avec les dossiers 2 et 3 et avec `--exclude` pour `duplicates_4.json`.
3. **Créer une version :** copier `criteria.json`, `labels.json`, `probes.pt` et les scores dans un dossier `myurbex-ai/models/2026-11-15/`. Ces fichiers vont toujours ensemble, et un tag Git suffit à les versionner.
4. **Déployer ou revenir en arrière :** écrire la version dans `models/current.txt` et relancer le service.

```text
python train_probes.py --evaluate --data D:\_Urbex\_tmpEntrainementMdl_4 expected_4.json --data D:\_Urbex\Urbex_Site\imgs expected_myurbex.json
```

Le réentraînement se lance par lots, par exemple toutes les quelques centaines de nouvelles photos, et non à chaque photo.

| Changement | Travail |
|---|---|
| Nouvelles photos | Réentraîner, sans toucher au code |
| Nouveau critère ou nouvelle option | Modifier `criteria.json` et `labels.json`, puis réentraîner |
| Autre modèle CLIP | Refaire tous les embeddings, puis réévaluer |

## 5. Pièges à traiter

| Piège | Risque | Réponse |
|---|---|---|
| Scores trop optimistes | Des photos d'un même lieu se retrouvaient à la fois dans l'entraînement et dans le test. | Corrigé : voir la section 7. Il reste à garder un jeu de test fixe, jamais utilisé pour l'entraînement. |
| Cache des embeddings | Son nom dépendait seulement du nom du dossier. Après un changement de CLIP, il aurait réutilisé d'anciens embeddings sans prévenir. | Corrigé : voir la section 7 |
| Réponses acceptées sans vérification | Elles enseignent au modèle ses propres erreurs. | Distinguer « accepté » et « corrigé », et n'entraîner d'abord que sur les réponses vérifiées |
| Doublons entre dossiers | Les photos de `_tmpEntrainementMdl_*` sont peut-être aussi dans `imgs` (non vérifié). Elles compteraient deux fois. | Dédoublonner par empreinte de fichier |
| Sauvegarde | `photos/` est ignoré par Git et les dossiers `_tmpEntrainementMdl_*` sont hors du dépôt. Sans ces images, `expected_*.json` ne suffit pas pour réentraîner. | Sauvegarder ces dossiers |
| Version de CLIP | Une mise à jour peut changer les résultats. | Fait dans `myurbex-ai` : révision Hugging Face et dépendances figées. `requirements.txt` de `sandbox` reste sans version. |
| Modification de `analyzer.py` | Ce fichier sert à la fois au service et à l'entraînement : un changement agit sur les deux. | Réévaluer le modèle après toute modification |
| Type de lieu | L'IA décrit une photo, alors que `marker_type` décrit un lieu. Leurs valeurs n'ont pas encore été comparées. | Ne pas remplir automatiquement l'un avec l'autre avant cette comparaison |

## 6. Ordre de travail

1. **Lot 1, sans toucher au back ni au front :** projet `myurbex-ai` (fait), correction du cache et des plis (fait), puis mesure définitive et réentraînement après la passe sur `review.html` (à faire).
2. **Lot 2 :** endpoints d'écriture et envoi des photos.
3. **Lot 3 :** table `image_ai`, relais Spring et suggestions dans le formulaire Angular.
4. **Lot 4 :** export admin et premier réentraînement avec les données de MyUrbex.

Le lot 1 passe en premier parce qu'il ne dépend pas du reste et qu'il donne un vrai score de départ.

## 7. Modifications réalisées le 31 octobre 2026

### Projet myurbex-ai

- **Service :** `service.py` analyse une photo sans rien garder, sur `127.0.0.1:8001`, et limite les photos à 30 Mo.
- **Modèle :** `models/2026-10-31/` contient une copie de `criteria.json`, `labels.json` et `probes.pt`. `models/current.txt` donne la version servie.
- **Versions :** dépendances figées dans `requirements.txt`, et révision de CLIP figée dans `analyzer.py`.
- **Dépôt :** Git initialisé, avec un `.venv` propre de 914 Mo et un `README.md`.

### Projet sandbox

- **Code partagé :** le code d'analyse de `test_clip.py` est passé dans `myurbex-ai/analyzer.py`. `test_clip.py`, `train_probes.py`, `review_page.py` et `server.py` l'importent.
- **Installation :** `requirements.txt` pointe vers `D:/_Urbex/myurbex/myurbex-ai`, qui doit donc rester à sa place.
- **Cache :** son nom contient maintenant le modèle, sa révision et le chemin complet du dossier. Les 9 fichiers existants ont été renommés, donc aucun embedding n'a été recalculé.
- **Plis :** `train_probes.py` garde les photos d'un même lieu dans le même paquet.
- **Nouveau fichier :** `places.json` associe 2 136 noms de photos à un `marker_id`, depuis la sauvegarde `urbex-before-V3-2026-10-19.sql`.

### Regroupement par lieu

Le lieu d'une photo vient de la première source disponible :

1. `places.json`, seulement pour un nom qui désigne un seul lieu. Les 67 noms ambigus, comme certains `DSC…`, sont écartés.
2. Le lieu principal de son sous-dossier, ou à défaut le sous-dossier lui-même.
3. Le lieu principal de sa visite, ou à défaut la visite elle-même. Une visite regroupe les photos prises à moins de 3 h d'écart.

Une première version reliait tous ces indices entre eux. Elle formait un groupe géant de 3 292 photos, d'où cette règle plus simple.

Résultat : 5 267 photos, 359 groupes, un plus grand groupe de 242 photos et 5 paquets de 1 053 ou 1 054 photos.

### Scores

Les chiffres d'avant viennent du compte rendu du 31 octobre. Ceux d'après sont mesurés sur les dossiers 2, 3 et 4 avec le même λ de 0,01.

| Critère | Avant | Après |
|---|---|---|
| Type | 88,3 % | 84,1 % |
| Type de véhicule | 96,5 % | 91,9 % |
| Intérieur / extérieur | 97,6 % | 97,0 % |
| Catégorie d'intérieur | 82,2 % | 76,0 % |
| Ciel | 98,2 % | 97,5 % |
| Moment de la journée | 99,3 % | 98,7 % |
| Météo | 86,4 % | 82,0 % |

Le modèle n'a pas changé : `probes.pt` est identique, et seule la mesure est plus honnête. Ces scores sont provisoires, car la passe sur `review.html` n'est pas finie.

### Vérifications

- Réponses et scores strictement identiques avant et après le déplacement du code, sur 5 vraies photos.
- Service lancé depuis son propre environnement : les trois routes répondent, avec les mêmes réponses que `sandbox`. L'analyse d'une photo a pris 607 ms sur CPU.
- Un fichier qui n'est pas une image renvoie 415, et un fichier de plus de 30 Mo renvoie 413.
- `requirements.txt` s'installe dans un environnement neuf.
- Les noms de cache diffèrent bien selon le modèle et selon le chemin.

### Limites

- **Lieux incertains :** seules 2 209 photos sur 5 267 ont un lieu connu par `places.json`. Pour une grande partie du dossier 4, le regroupement repose sur les visites : deux lieux visités le même jour peuvent se mélanger, et un lieu revisité sans lieu connu peut encore être coupé. 2 sous-dossiers sur 152 sont coupés.
- **Comparaison :** je suppose que le chiffre d'avant venait du même jeu de données, avec `duplicates_4.json` exclu.
- **Non testé :** `server.py` s'importe mais n'a pas été relancé, et l'entraînement complet n'a pas été exécuté, seule l'évaluation l'a été.
- **Photo remplacée :** le cache ne détecte pas une image remplacée par une autre du même nom.
- **`places.json` :** le script qui l'a généré n'est pas conservé. À terme, l'export de MyUrbex fournira directement le `marker_id`.
