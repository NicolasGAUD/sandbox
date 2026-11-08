"""Removes the photo files that a migration deletes from the database.

    V14: the photos of the places of the deleted types.
    V21 (--views): the satellite and Street View images, which the site no longer keeps.

A SQL migration cannot touch files, hence two steps around it:

    python delete_marker_files.py [--db urbex_test] list --out deleted_photos.json [--views]
        before the migration: writes the names of the photos it will delete
    python delete_marker_files.py [--db urbex_test] delete --list deleted_photos.json --images DIR --thumbs DIR
        after the migration: moves each photo and its thumbnail into the "_deleted" folder of its folder,
        as the backend does, and only when its row no longer exists in the database

Nothing is erased: the "_deleted" folders are emptied by hand.
"""

import argparse
import json
import shutil
from pathlib import Path

import pymysql

# The types removed by V14, with their places, photos and visits
DELETED_TYPES = ("GOU", "SCO", "RST", "OTH", "SPO", "AER", "SEM")
# The image types removed by V21
VIEW_TYPES = ("SAT", "STR")
DELETED_DIR = "_deleted"  # same folder as the backend's ImageFileService


def connect(args):
    return pymysql.connect(host=args.host, port=args.port, user=args.user, password=args.password,
                           database=args.db)


def photos_of_deleted_types(connection):
    placeholders = ", ".join(["%s"] * len(DELETED_TYPES))
    with connection.cursor() as cursor:
        cursor.execute(f"""SELECT i.name FROM image i
                           JOIN marker m ON m.id = i.marker_id
                           JOIN marker_type t ON t.id = m.marker_type_id
                           WHERE t.code_type IN ({placeholders}) ORDER BY i.name""", DELETED_TYPES)
        return [name for (name,) in cursor.fetchall()]


def satellite_and_street_views(connection):
    placeholders = ", ".join(["%s"] * len(VIEW_TYPES))
    with connection.cursor() as cursor:
        cursor.execute(f"""SELECT i.name FROM image i
                           JOIN image_type t ON t.id = i.image_type_id
                           WHERE t.code_type IN ({placeholders}) ORDER BY i.name""", VIEW_TYPES)
        return [name for (name,) in cursor.fetchall()]


def still_in_database(connection, name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM image WHERE name = %s", (name,))
        return cursor.fetchone()[0] > 0


def move_to_deleted(folder, name):
    """True when the file existed and was moved. Never leaves the folder, whatever the name."""
    folder = folder.resolve()
    source = (folder / name).resolve()
    if not source.is_relative_to(folder) or not source.is_file():
        return False
    target = folder / DELETED_DIR / source.relative_to(folder)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(source, target)
    return True


def list_photos(args):
    with connect(args) as connection:
        names = satellite_and_street_views(connection) if args.views else photos_of_deleted_types(connection)
    Path(args.out).write_text(json.dumps(names, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(names)} photos listed in {args.out}")


def delete_photos(args):
    names = json.loads(Path(args.list).read_text(encoding="utf-8"))
    moved = {"photos": 0, "thumbnails": 0}
    kept = []
    with connect(args) as connection:
        for name in names:
            if still_in_database(connection, name):
                kept.append(name)
                continue
            moved["photos"] += move_to_deleted(Path(args.images), name)
            moved["thumbnails"] += move_to_deleted(Path(args.thumbs), name)
    print(f"{moved['photos']} photos and {moved['thumbnails']} thumbnails moved to {DELETED_DIR}")
    if kept:
        print(f"{len(kept)} photos kept, still in the database (migration not applied?):")
        for name in kept:
            print(f"  {name}")


def main():
    parser = argparse.ArgumentParser(description="Photo files deleted by V14 or V21.")
    parser.add_argument("--db", default="urbex_test")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=3307)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    steps = parser.add_subparsers(dest="step", required=True)
    listing = steps.add_parser("list", help="before the migration")
    listing.add_argument("--out", required=True)
    listing.add_argument("--views", action="store_true", help="the satellite and Street View images (V21)")
    deleting = steps.add_parser("delete", help="after the migration")
    deleting.add_argument("--list", required=True)
    deleting.add_argument("--images", required=True)
    deleting.add_argument("--thumbs", required=True)
    args = parser.parse_args()
    list_photos(args) if args.step == "list" else delete_photos(args)


if __name__ == "__main__":
    main()
