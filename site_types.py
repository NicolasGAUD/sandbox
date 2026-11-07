"""Fills the "site_type" answer of the expected files from the MyUrbex database: the marker_type code
of the place each photo belongs to.

Usage:
    python site_types.py expected_2.json expected_3.json expected_4.json [--db urbex_test] [--port 3307]

A photo gets the code of its place when places.json gives its marker and that marker's type is one of
the options of "site_type" in criteria.json. Otherwise its "site_type" answer is removed. The database
is only read.
"""

import argparse
import json
from pathlib import Path

import pymysql

HERE = Path(__file__).parent


def marker_types(host, port, user, password, database):
    """{marker id: marker_type code}."""
    connection = pymysql.connect(host=host, port=port, user=user, password=password, database=database)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT m.id, t.code_type FROM marker m JOIN marker_type t ON t.id = m.marker_type_id")
            return dict(cursor.fetchall())
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description="Fills site_type in the expected files from the database.")
    parser.add_argument("expected", type=Path, nargs="+")
    parser.add_argument("--criteria", type=Path, default=HERE / "criteria.json")
    parser.add_argument("--places", type=Path, default=HERE / "places.json")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=3307)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--db", default="urbex_test")  # at V14: REL and its sub-types
    args = parser.parse_args()

    criteria = json.loads(args.criteria.read_text(encoding="utf-8"))
    codes = set(next(c for c in criteria["choices"] if c["name"] == "site_type")["options"])
    places = json.loads(args.places.read_text(encoding="utf-8"))
    types = marker_types(args.host, args.port, args.user, args.password, args.db)

    for path in args.expected:
        raw = path.read_text(encoding="utf-8")
        expected = json.loads(raw)
        filled = 0
        for name, answers in expected.items():
            code = types.get(places.get(Path(name).name))
            if code in codes:
                answers["site_type"] = code
                filled += 1
            else:
                answers.pop("site_type", None)
        text = json.dumps(expected, ensure_ascii=False, indent=2) + ("\n" if raw.endswith("\n") else "")
        path.write_text(text, encoding="utf-8", newline="")
        print(f"{path.name}: site_type on {filled} of {len(expected)} photos")


if __name__ == "__main__":
    main()
