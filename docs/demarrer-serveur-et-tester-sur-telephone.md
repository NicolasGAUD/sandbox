# Démarrer le serveur et tester sur le téléphone

**Application :** CLIP urbex (branche `feature/photo-upload-app`)
**Date :** 25 octobre 2026

Le plus simple est de passer par le fichier `start_server.bat`, sans ouvrir WebStorm.

## 1. Démarrer le serveur

Dans l'Explorateur Windows, ouvrir `D:\WebstormProjects\sandbox` et double-cliquer sur `start_server.bat`.

Une fenêtre noire s'ouvre. Après quelques secondes, le temps de charger le modèle, le serveur est prêt quand cette ligne apparaît :

```
Uvicorn running on http://0.0.0.0:8000
```

Laisser cette fenêtre ouverte pendant tout le test.

Sans double-clic, on peut aussi le lancer depuis un terminal (Win + X → « Terminal ») :

```
cd D:\WebstormProjects\sandbox
.\start_server.bat
```

## 2. Trouver l'adresse du PC

Dans un terminal, taper `ipconfig` et relever l'« Adresse IPv4 » de la carte Wi-Fi, par exemple `192.168.1.167`. La box peut la changer après un redémarrage : la vérifier si la page ne s'ouvre plus.

## 3. Tester sur le téléphone

1. Connecter le téléphone au même Wi-Fi que le PC.
2. Ouvrir le navigateur et aller sur `http://192.168.1.167:8000/` (ou l'adresse relevée à l'étape 2).
3. Appuyer sur « Prendre une photo » ou « Parcourir… », corriger les réponses si besoin, puis appuyer sur « Valider ».

Les photos validées arrivent dans `D:\WebstormProjects\sandbox\photos\`, avec leurs réponses dans `expected.json`. Elles sont nommées d'après leur date de prise de vue, par exemple `2026-08-31_09-20-45.jpg`.

## 4. Arrêter le serveur

Fermer la fenêtre noire, ou appuyer sur Ctrl+C dedans.

## Si ça ne marche pas

- **La fenêtre affiche « Application non compilée » :** aller dans le dossier `app` et lancer `npm run build`, puis relancer le `.bat`.
- **Il n'y a pas de `start_server.bat` :** le projet est sur la branche `main`. Le fichier et l'application sont sur la branche `feature/photo-upload-app`. Pour y revenir, taper `git switch feature/photo-upload-app` dans le dossier du projet.
- **Le téléphone n'arrive pas à ouvrir la page :**
  - vérifier que le téléphone est sur le même Wi-Fi ;
  - vérifier que l'adresse utilisée est l'adresse IPv4 du moment ;
  - regarder si Windows a affiché une alerte de pare-feu pour Python : il faut alors l'autoriser.
