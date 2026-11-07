"""HTTP API used by the Angular app (app/): analyses an uploaded photo, then files it once validated.

Usage:
    python server.py [--photos photos] [--host 0.0.0.0] [--port 8000]

    POST /api/analyses                 photo (multipart "photo") -> CLIP answers for every criterion, EXIF
    POST /api/analyses/{id}/validate   {"answers": {...}} -> photo copied into --photos, answers saved
    GET  /api/config                   shown criteria and FR/EN labels

The photo waits in uploads/ until it is validated; it is then copied into the photos folder and
its answers are added to <photos>/expected.json (same format as expected_*.json, so the folder
can be used by test_clip.py and train_probes.py). When the app has been built (npm run build in
app/), it is served at the root, so a phone on the same network only needs http://<pc>:8000/.
"""

import argparse
import io
import json
import shutil
import threading
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

from analyzer import Analyzer, analysis_answers, criteria_config
from labels import load_labels
from photo_exif import exif_for_page, read_exif
from test_clip import EXTENSIONS

HERE = Path(__file__).parent
UPLOADS = HERE / "uploads"
APP_BUILD = HERE / "app" / "dist" / "app" / "browser"


def file_name(taken, suffix):
    """Timestamp in milliseconds: of the shooting date, otherwise of the upload, e.g. 1497097388000.jpg.

    Phone cameras often call every photo "image.jpg": the original name is never kept.
    """
    moment = taken.timestamp() if taken else time.time()
    return f"{round(moment * 1000)}{suffix}"


class Validation(BaseModel):
    answers: dict[str, str | None]


def create_app(analyzer, photos, criteria_path):
    with open(criteria_path, encoding="utf-8") as f:
        criteria = json.load(f)
    config = {"criteria": criteria_config(criteria), "labels": load_labels()}
    pending = {}  # id -> uploaded file and original name, until validated
    shutil.rmtree(UPLOADS, ignore_errors=True)  # photos left unvalidated by an earlier run
    lock = threading.Lock()  # one analysis at a time: the model is shared
    api = FastAPI(title="CLIP urbex")

    @api.get("/api/config")
    def get_config():
        return config

    # Plain "def" endpoints run in a worker thread: the analysis does not block the server.
    @api.post("/api/analyses")
    def analyse(photo: UploadFile = File(...)):
        name = Path(photo.filename or "photo.jpg").name
        suffix = Path(name).suffix.lower()
        if suffix not in EXTENSIONS:
            suffix = ".jpg"
        content = photo.file.read()
        try:
            image = ImageOps.exif_transpose(Image.open(io.BytesIO(content))).convert("RGB")
        except UnidentifiedImageError:
            raise HTTPException(415, "unreadable image")
        start = time.perf_counter()
        with lock:
            results, details, _ = analyzer.analyse(image, all_details=True)
        time_ms = (time.perf_counter() - start) * 1000

        analysis_id = uuid.uuid4().hex
        UPLOADS.mkdir(exist_ok=True)
        path = UPLOADS / f"{analysis_id}{suffix}"
        path.write_bytes(content)
        exif = read_exif(io.BytesIO(content))
        pending[analysis_id] = {"path": path, "name": file_name(exif["taken"], suffix)}
        return {"id": analysis_id, "name": name, "time_ms": round(time_ms),
                "answers": analysis_answers(config["criteria"], results, details),
                "exif": exif_for_page(exif)}

    @api.post("/api/analyses/{analysis_id}/validate")
    def validate(analysis_id: str, validation: Validation):
        if analysis_id not in pending:
            raise HTTPException(404, "unknown analysis")
        upload = pending.pop(analysis_id)
        photos.mkdir(parents=True, exist_ok=True)
        # Never overwrite a photo already filed: "name (2).jpg", "name (3).jpg"…
        target, n = photos / upload["name"], 1
        while target.exists():
            n += 1
            target = photos / f"{Path(upload['name']).stem} ({n}){Path(upload['name']).suffix}"
        shutil.move(upload["path"], target)

        expected_path = photos / "expected.json"
        expected = json.loads(expected_path.read_text(encoding="utf-8")) if expected_path.exists() else {}
        names = [c["name"] for c in config["criteria"]]
        expected[target.name] = {name: validation.answers.get(name) for name in names}
        expected_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"file": target.name}

    if APP_BUILD.exists():
        api.mount("/", StaticFiles(directory=APP_BUILD, html=True), name="app")
    else:
        @api.get("/")
        def no_build():
            return {"message": "app not built: run 'npm run build' in app/, or 'npm start' for development"}

    return api


def main():
    parser = argparse.ArgumentParser(description="API of the photo analysis app.")
    parser.add_argument("--photos", type=Path, default=HERE / "photos", help="folder where validated photos go")
    parser.add_argument("--criteria", type=Path, default=HERE / "criteria.json")
    parser.add_argument("--probes", type=Path, default=HERE / "probes.pt")
    parser.add_argument("--host", default="0.0.0.0", help="0.0.0.0: reachable from a phone on the same network")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    analyzer = Analyzer(args.criteria, args.probes)
    uvicorn.run(create_app(analyzer, args.photos, args.criteria), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
