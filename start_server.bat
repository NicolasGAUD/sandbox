@echo off
REM ============================================================================
REM  Comment démarrer le serveur en dehors de WebStorm ?
REM
REM  Double-cliquer sur ce fichier, ou ouvrir un terminal Windows (PowerShell,
REM  par exemple avec Win + X → « Terminal »), puis taper :
REM
REM    cd D:\WebstormProjects\sandbox
REM    .venv\Scripts\python.exe server.py --photos D:\WebstormProjects\sandbox\photos
REM
REM  - Démarrage : il faut quelques secondes pour charger le modèle. Le serveur
REM    est prêt quand la ligne « Uvicorn running on http://0.0.0.0:8000 » apparaît.
REM  - Depuis le PC : ouvrir http://localhost:8000/
REM  - Depuis le téléphone : ouvrir http://<IP du PC>:8000/, avec le téléphone
REM    sur le même Wi-Fi. La commande ipconfig donne l'adresse IPv4 du PC.
REM  - Arrêt : Ctrl+C dans ce terminal, ou fermer simplement la fenêtre.
REM
REM  Points à savoir :
REM  - Application compilée : le serveur sert la version compilée de
REM    l'application, qui se trouve dans app\dist. Après une modification du code
REM    Angular, relancer la compilation avec « cd app » puis « npm run build ».
REM  - Pare-feu : au premier lancement, Windows peut demander d'autoriser Python.
REM    Accepter au moins pour les réseaux privés, sinon le téléphone ne pourra
REM    pas joindre le PC.
REM  - Autre dossier : --photos choisit le dossier où sont rangées les photos
REM    validées. Sans cette option, c'est photos\ dans le projet.
REM ============================================================================

REM Le dossier de ce fichier (le projet), quel que soit l'endroit d'où il est lancé.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

if not exist "app\dist\app\browser\index.html" (
    echo Application non compilee : lancer "npm run build" dans le dossier app, puis relancer ce fichier.
    pause
    exit /b 1
)

.venv\Scripts\python.exe server.py --photos "%~dp0photos"

REM La fenêtre reste ouverte si le serveur s'arrête sur une erreur, pour pouvoir la lire.
if errorlevel 1 pause
