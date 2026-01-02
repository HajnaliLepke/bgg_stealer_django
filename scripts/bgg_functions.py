from __future__ import annotations

from dataclasses import dataclass, asdict
from dotenv import load_dotenv
import os
import time
import json
import logging
import sys
import re
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, List

import django
import requests
import xml.etree.ElementTree as ET


# ----------------------------
# Models (type safety)
# ----------------------------
@dataclass
class OwnedGameRef:
    """Minimal game info from /collection (owned only)."""
    objectid: str
    name: Optional[str]
    owners: str  # comma-separated list of owners (keeps your current behavior)

    def add_owner(self, username: str) -> None:
        if not self.owners:
            self.owners = username
        elif username not in self.owners.split(","):
            self.owners += "," + username


@dataclass
class GameDetails:
    """Enriched game info from /thing?stats=1."""
    objectid: str
    name: Optional[str]              # name from collection (your "display name")
    primary_name: Optional[str]      # BGG primary name
    owners: str

    type: Optional[str]
    image: Optional[str]

    yearpublished: Optional[int]
    minplayers: Optional[int]
    maxplayers: Optional[int]
    minplaytime: Optional[int]
    maxplaytime: Optional[int]

    rating: Optional[float]
    weight: Optional[float]
    rank: Optional[int]


# ----------------------------
# Logging setup
# ----------------------------
def setup_logging(log_file: str = "bgg_import.log") -> logging.Logger:
    logger = logging.getLogger("bgg_import")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    fh = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    if not logger.handlers:
        logger.addHandler(ch)
        logger.addHandler(fh)

    return logger


logger = setup_logging()


class Timer:
    """Context manager for timing."""
    def __init__(self, label: str):
        self.label = label
        self.t0 = 0.0

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = time.perf_counter() - self.t0
        logger.info("%s | took %.3fs", self.label, dt)


# ----------------------------
# Env
# ----------------------------
load_dotenv()
BGG_TOKEN = os.getenv("BGG_TOKEN")
if not BGG_TOKEN:
    raise RuntimeError("Missing BGG_TOKEN env var. Set it before running the importer.")

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

# ----------------------------
# Helpers
# ----------------------------
def normalize_kind(itemtype: str) -> str:
    s = (itemtype or "").strip().lower()
    # adjust these mappings if your CSV uses different values
    if s in {"standalone", "boardgame", "game"}:
        return "STANDALONE"
    if s in {"expansion", "boardgameexpansion"}:
        return "EXPANSION"
    return "OTHER"

def _to_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() in {"nan", "not ranked"}:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() in {"nan"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _text_strip(el: Optional[ET.Element]) -> Optional[str]:
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


# ----------------------------
# BGG Calls
# ----------------------------
def fetch_bgg_user_collection(username: str, *, tries: int = 5, sleep_seconds: float = 1.0) -> Optional[str]:
    url = "https://boardgamegeek.com/xmlapi2/collection"
    params = {"username": str(username)}
    headers = {
        "User-Agent": "gamekeep-import/1.0 (personal project)",
        "Authorization": f"Bearer {BGG_TOKEN}",
    }

    for attempt in range(1, tries + 1):
        t0 = time.perf_counter()
        try:
            r = requests.get(url, params=params, headers=headers, timeout=20)
        except requests.RequestException as e:
            dt = time.perf_counter() - t0
            logger.warning("collection | user=%s | attempt=%d/%d | EXCEPTION after %.3fs | %s",
                           username, attempt, tries, dt, e)
            time.sleep(sleep_seconds)
            continue

        dt = time.perf_counter() - t0
        size = len(r.content) if r.content is not None else 0
        logger.info("collection | user=%s | attempt=%d/%d | status=%s | bytes=%d | %.3fs",
                    username, attempt, tries, r.status_code, size, dt)

        if r.status_code != 200:
            time.sleep(sleep_seconds)
            continue

        text = (r.text or "").strip()
        if not text:
            logger.info("collection | user=%s | attempt=%d/%d | empty body -> retry",
                        username, attempt, tries)
            time.sleep(sleep_seconds)
            continue

        return text

    logger.error("collection | user=%s | FAILED after %d tries", username, tries)
    return None


def fetch_bgg_thing_details(game: OwnedGameRef, *, tries: int = 5, sleep_seconds: float = 1.0) -> Optional[GameDetails]:
    url = "https://boardgamegeek.com/xmlapi2/thing"
    params = {"id": game.objectid, "stats": "1", "versions":"1"}
    headers = {
        "User-Agent": "gamekeep-import/1.0 (personal project)",
        "Authorization": f"Bearer {BGG_TOKEN}",
    }

    for attempt in range(1, tries + 1):
        t0 = time.perf_counter()
        try:
            r = requests.get(url, params=params, headers=headers, timeout=20)
        except requests.RequestException as e:
            dt = time.perf_counter() - t0
            logger.warning("thing | id=%s | owners=%s | attempt=%d/%d | EXCEPTION after %.3fs | %s",
                           game.objectid, game.owners, attempt, tries, dt, e)
            time.sleep(sleep_seconds)
            continue

        dt = time.perf_counter() - t0
        size = len(r.content) if r.content is not None else 0
        logger.info("thing | id=%s | attempt=%d/%d | status=%s | bytes=%d | %.3fs",
                    game.objectid, attempt, tries, r.status_code, size, dt)

        if r.status_code != 200:
            time.sleep(sleep_seconds)
            continue

        text = (r.text or "").strip()
        if not text:
            logger.info("thing | id=%s | attempt=%d/%d | empty body -> retry",
                        game.objectid, attempt, tries)
            time.sleep(sleep_seconds)
            continue

        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            logger.error("thing | id=%s | XML ParseError: %s", game.objectid, e)
            return None

        item = root.find("item")
        if item is None:
            logger.warning("thing | id=%s | no <item> found", game.objectid)
            return None

        # primary name
        primary_name = None
        for name_el in item.findall("name"):
            if name_el.get("type") == "primary":
                primary_name = name_el.get("value")
                break

        image = _text_strip(item.find("image"))

        year = _to_int(item.find("yearpublished").get("value")) if item.find("yearpublished") is not None else None
        minp = _to_int(item.find("minplayers").get("value")) if item.find("minplayers") is not None else None
        maxp = _to_int(item.find("maxplayers").get("value")) if item.find("maxplayers") is not None else None
        minpt = _to_int(item.find("minplaytime").get("value")) if item.find("minplaytime") is not None else None
        maxpt = _to_int(item.find("maxplaytime").get("value")) if item.find("maxplaytime") is not None else None

        ratings_el = item.find("statistics/ratings")
        rating = weight = None
        rank_val: Optional[int] = None

        if ratings_el is not None:
            rating = _to_float(ratings_el.find("average").get("value")) if ratings_el.find("average") is not None else None
            weight = _to_float(ratings_el.find("averageweight").get("value")) if ratings_el.find("averageweight") is not None else None

            ranks_el = ratings_el.find("ranks")
            if ranks_el is not None:
                for rk in ranks_el.findall("rank"):
                    if rk.get("id") == "1":
                        # Sometimes "Not Ranked"
                        rank_val = _to_int(rk.get("value"))
                        break

        return GameDetails(
            objectid=item.get("id") or game.objectid,
            name=game.name,
            primary_name=primary_name,
            owners=game.owners,
            type=item.get("type"),
            image=image,
            yearpublished=year,
            minplayers=minp,
            maxplayers=maxp,
            minplaytime=minpt,
            maxplaytime=maxpt,
            rating=rating,
            weight=weight,
            rank=rank_val,
        )

    logger.error("thing | id=%s | FAILED after %d tries", game.objectid, tries)
    return None


# ----------------------------
# Parse collection
# ----------------------------
def parse_bgg_collection(xml_text: str, username: str, games: Dict[str, OwnedGameRef]) -> Dict[str, OwnedGameRef]:
    root = ET.fromstring(xml_text)
    added = updated = scanned = 0

    for item in root.findall("item"):
        scanned += 1
        status = item.find("status")
        if status is None or status.get("own") != "1":
            continue

        objectid = item.get("objectid")
        if not objectid:
            continue
        objectid = objectid.strip()

        name_el = item.find("name")
        name = name_el.text.strip() if (name_el is not None and name_el.text) else None

        if objectid in games:
            games[objectid].add_owner(username)
            updated += 1
        else:
            games[objectid] = OwnedGameRef(objectid=objectid, name=name, owners=username)
            added += 1

    logger.info("parse | user=%s | scanned=%d | added=%d | updated=%d | total_unique=%d",
                username, scanned, added, updated, len(games))
    return games


# ----------------------------
# Main
# ----------------------------

def upload_bgg_games(owners: List[str], save_to_json: bool = False) -> None:
    games_simple: Dict[str, OwnedGameRef] = {}
    games_final: Dict[str, GameDetails] = {}

    with Timer("TOTAL OPERATION"):
        # Per-owner
        for o in owners:
            with Timer(f"OWNER {o} (collection+parse)"):
                logger.info("owner=%s | start", o)

                time.sleep(1)
                xml_text = fetch_bgg_user_collection(o)
                time.sleep(1)

                if not xml_text:
                    logger.error("owner=%s | collection fetch failed; skipping", o)
                    continue

                games_simple = parse_bgg_collection(xml_text, o, games_simple)

                logger.info("owner=%s | end", o)

        logger.info("collection phase done | unique owned games=%d", len(games_simple))

        # Per-game details
        for objectid, gref in list(games_simple.items()):
            with Timer(f"THING {objectid} (fetch+parse)"):
                logger.info("thing=%s | start | owners=%s", objectid, gref.owners)

                time.sleep(2)
                details = fetch_bgg_thing_details(gref)

                if details is None:
                    logger.error("thing=%s | failed; skipping enrichment", objectid)
                    continue

                games_final[objectid] = details
                logger.info("thing=%s | end", objectid)
                break

    # Save JSON (final)
    if save_to_json:
        out_file = "bgg_everything.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(
                {oid: asdict(game) for oid, game in games_final.items()},
                f,
                indent=2,
                ensure_ascii=False,
            )

        logger.info("saved %d enriched games to %s", len(games_final), out_file)
    
    created = 0
    updated = 0
    for objectid, object in games_final.items():
        with Timer(f"THING {objectid}:{object.name} (django create)"):

            defaults_for_game = {
                "title_local": (object.name or "").strip(),
                "title": (object.primary_name or "").strip(),
                "version_nickname": ("").strip(),

                "rating": object.rating,
                "weight": object.weight,
                "rank": object.rank,
                "year": object.yearpublished,

                "min_players": object.minplayers,
                "max_players": object.maxplayers,
                "min_playing_time": object.minplaytime,
                "max_playing_time": object.maxplaytime,

                "kind": normalize_kind(object.type),
                "image_url": object.image
            }


            game, was_created = BoardGame.objects.update_or_create(
                objectid=objectid,
                title=object.name,
                defaults=defaults_for_game,
            )
            for owner in object.owners.split(","):
                owner_obj, _ = Owner.objects.get_or_create(
                    slug=owner,
                    defaults={"name": owner},
                )
                OwnerInventory.objects.get_or_create(owner=owner_obj, game=game)


            if was_created:
                created += 1
            else:
                updated += 1
    logger.info("django create | created=%d | updated=%d | total_unique=%d",
                created, updated, len(games_final))

owners: List[str] = ["Boardgamebudapest", "gemklub_corvin", "jatszma_kavezo", "jatszohazprojekt"]
upload_bgg_games(owners,True)