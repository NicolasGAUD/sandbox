# CLIP urbex app

Mobile web app: take or choose a photo, check CLIP's answers, correct them, validate.
The photo is analysed by `server.py` (repository root), then filed with its answers once validated.

## Run it on a phone

1. Build the app once (and after each change): `npm install` then `npm run build`, in this folder.
2. Start the server from the repository root:
   `.venv/Scripts/python.exe server.py --photos D:/path/to/folder`
3. On the phone (same Wi-Fi as the PC), open `http://<PC address>:8000/`.
   The PC address is given by `ipconfig` (IPv4). Windows may ask to allow Python through the firewall.

Validated photos are copied into the `--photos` folder (default `photos/`) and their answers are
added to `expected.json` in that folder, in the same format as `expected_*.json`.

## Develop

`npm start` serves the app with live reload on port 4200 and forwards `/api` to `server.py` on port 8000.
