"""Checks the AI criteria against the place types of the MyUrbex database: the ai_value columns of
marker_type and marker_subtype.

Usage:
    python sync_criteria_from_db.py [--db urbex_test] [--port 3307]

- Every ai_value of the database must be an option of a criterion of criteria.json: the AI can then
  answer it. One without an option stops the script (exit code 1): its prompt is to write by hand,
  then the probes to train again.
- Every such value needs its label in labels.json ("values" of its criterion). A missing one is printed
  as the line to paste there, from the database (label for fr, label_en for en).
- The options of place_type and vehicle_type without a type or sub-type in the database are listed:
  they describe a photo only (a rooftop), nothing to do.

The database is only read.
"""

import argparse
import json
import sys
from pathlib import Path

import pymysql

HERE = Path(__file__).parent

# The criteria whose values name a type or a sub-type
PLACE_CRITERIA = ("place_type", "vehicle_type")
# Its options are the codes themselves, not ai_values
CODES_CRITERION = "site_type"


def database_values(host, port, user, password, database):
    """[(table, code, ai_value, label, label_en)] of the types and sub-types that have an ai_value."""
    connection = pymysql.connect(host=host, port=port, user=user, password=password, database=database)
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 'marker_type', code_type, ai_value, label, label_en FROM marker_type
                WHERE ai_value IS NOT NULL
                UNION ALL
                SELECT 'marker_subtype', code_subtype, ai_value, label, label_en FROM marker_subtype
                WHERE ai_value IS NOT NULL
                ORDER BY 3
                """)
            return list(cursor.fetchall())
    finally:
        connection.close()


def criterion_of(choices):
    """{value: name of its criterion}, the first criterion that may answer it: its options, the values it
    gets in some cases (values_if, a sculpture for plastic arts) and those only typed in (manual_values)."""
    found = {}
    for choice in choices:
        if choice["name"] == CODES_CRITERION:
            continue
        values = list(choice["options"]) + choice.get("manual_values", [])
        for by_value in choice.get("values_if", {}).values():
            for added in by_value.values():
                values += added
        for value in values:
            found.setdefault(value, choice["name"])
    return found


def main():
    parser = argparse.ArgumentParser(description="Checks the AI criteria against the ai_value of the database.")
    parser.add_argument("--criteria", type=Path, default=HERE / "criteria.json")
    parser.add_argument("--labels", type=Path, default=HERE / "labels.json")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=3307)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--db", default="urbex_test")
    args = parser.parse_args()

    criteria = json.loads(args.criteria.read_text(encoding="utf-8"))
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    rows = database_values(args.host, args.port, args.user, args.password, args.db)
    options = criterion_of(criteria["choices"])

    without_option = [row for row in rows if row[2] not in options]
    for table, code, ai_value, _, _ in without_option:
        print(f"NO OPTION   {table} {code}: {ai_value!r} is in no criterion, its prompt is to write")

    missing_labels = 0
    for table, code, ai_value, label, label_en in rows:
        criterion = options.get(ai_value)
        if criterion and ai_value not in labels["values"].get(criterion, {}):
            missing_labels += 1
            line = json.dumps({ai_value: {"en": label_en or label, "fr": label}}, ensure_ascii=False)[1:-1]
            print(f"NO LABEL    {table} {code}, to paste in values.{criterion}: {line},")

    in_database = {row[2] for row in rows}
    for choice in criteria["choices"]:
        if choice["name"] in PLACE_CRITERIA:
            for option in choice["options"]:
                if option not in in_database:
                    print(f"PHOTO ONLY  {choice['name']}.{option}: no type or sub-type in the database")

    print(f"{len(rows)} ai_values in {args.db}, {len(without_option)} without option, "
          f"{missing_labels} without label")
    sys.exit(1 if without_option else 0)


if __name__ == "__main__":
    main()
