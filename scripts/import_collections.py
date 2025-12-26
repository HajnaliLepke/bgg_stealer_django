import csv
import os
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import django



def to_int(v):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def to_positive_int(v, *, min_value=1, max_value=None):
    n = to_int(v)
    if n is None:
        return None
    if n < min_value:
        return None
    if max_value is not None and n > max_value:
        return None
    return n

def to_decimal(v):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        return Decimal(v)
    except (InvalidOperation, ValueError):
        return None

def normalize_kind(itemtype: str) -> str:
    s = (itemtype or "").strip().lower()
    # adjust these mappings if your CSV uses different values
    if s in {"standalone", "boardgame", "game"}:
        return "STANDALONE"
    if s in {"expansion", "boardgameexpansion"}:
        return "EXPANSION"
    return "OTHER"


def owner_from_filename(filename: str) -> str:
    # expects: collection_[owner].csv
    m = re.match(r"^collection_(.+)\.csv$", Path(filename).name)
    if not m:
        raise ValueError(f"Unexpected filename format: {filename}")
    return m.group(1)


def main():

    # ------------------------------------------------------------
    # Django setup (auto-detect from manage.py)
    # ------------------------------------------------------------

    BASE_DIR = Path(__file__).resolve().parent.parent

    # Ensure project root is on PYTHONPATH
    sys.path.insert(0, str(BASE_DIR))

    # Read DJANGO_SETTINGS_MODULE from manage.py
    manage_py = BASE_DIR / "manage.py"
    text = manage_py.read_text(encoding="utf-8")
    m = re.search(r"DJANGO_SETTINGS_MODULE',\s*'([^']+)'", text)
    if not m:
        raise RuntimeError("Could not detect DJANGO_SETTINGS_MODULE from manage.py")

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", m.group(1))

    django.setup()

    from accounts.models import Owner, BoardGame, OwnerInventory

    # base_dir = Path(__file__).resolve().parent.parent
    base_dir = Path("./data/").resolve()
    data_dir = base_dir  # put CSVs in project root by default; change if you use another folder

    csv_files = sorted(data_dir.glob("collection_*.csv"))
    if not csv_files:
        print(f"No CSV files found in {data_dir} matching collection_*.csv")
        return

    created = 0
    updated = 0

    for csv_path in csv_files:
        owner = owner_from_filename(csv_path.name)
        
        owner_obj, _ = Owner.objects.get_or_create(
            slug=owner,
            defaults={"name": owner},
        )



        print(f"Importing {csv_path.name} (owner={owner})")


        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            for row in reader:
                objectid = to_positive_int(row.get("objectid"), min_value=1)
                if objectid is None:
                    continue

                title = (row.get("originalname") or "").strip() or (row.get("objectname") or "").strip()

                defaults_for_game = {
                    "title_local": (row.get("objectname") or "").strip(),
                    "title": title,
                    "version_nickname": (row.get("version_nickname") or "").strip(),

                    "rating": to_decimal(row.get("average")),
                    "weight": to_decimal(row.get("avgweight")),
                    "rank": to_positive_int(row.get("rank")),
                    "year": to_positive_int(row.get("yearpublished")),

                    "min_players": to_positive_int(row.get("minplayers")),
                    "max_players": to_positive_int(row.get("maxplayers")),
                    "min_playing_time": to_positive_int(row.get("minplaytime")),
                    "max_playing_time": to_positive_int(row.get("maxplaytime")),

                    "kind": normalize_kind(row.get("itemtype")),
                    "image_url": "https://cf.geekdo-images.com/yLZJCVLlIx4c7eJEWUNJ7w__imagepage/img/uIjeoKgHMcRtzRSR4MoUYl3nXxs=/fit-in/900x600/filters:no_upscale():strip_icc()/pic4458123.jpg"
                }
                if defaults_for_game["year"] is None and (row.get("yearpublished") or "").strip():
                    print(f"  - bad yearpublished='{row.get('yearpublished')}' for objectid={objectid} title='{defaults_for_game['title']}'")


                game, was_created = BoardGame.objects.update_or_create(
                    objectid=objectid,
                    title=title,
                    defaults=defaults_for_game,
                )
                OwnerInventory.objects.get_or_create(owner=owner_obj, game=game)


                if was_created:
                    created += 1
                else:
                    updated += 1

    print(f"Done. Created: {created}, Updated: {updated}")


if __name__ == "__main__":
    main()
