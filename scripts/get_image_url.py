import time
import requests
import xml.etree.ElementTree as ET

def fetch_bgg_image_url(objectid: int, *, tries: int = 5, sleep_seconds: float = 1.5) -> str | None:
    """
    Returns the representative image URL for a BGG thing (boardgame) via XMLAPI2.
    Retries because BGG can queue requests.
    """
    url = "https://boardgamegeek.com/xmlapi2/thing"
    params = {"id": str(objectid)}
    headers = {"User-Agent": "gamekeep-import/1.0 (personal project)"}

    for attempt in range(tries):
        r = requests.get(url, params=params, headers=headers, timeout=20)

        # XMLAPI2 sometimes returns a queued response; just retry
        print(r.status_code)
        if r.status_code != 200:
            time.sleep(sleep_seconds)
            continue

        print(r.text)

        text = r.text.strip()
        if not text:
            time.sleep(sleep_seconds)
            continue

        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            time.sleep(sleep_seconds)
            continue

        item = root.find("item")
        if item is None:
            time.sleep(sleep_seconds)
            continue

        image_el = item.find("image")
        if image_el is not None and (image_el.text or "").strip():
            return image_el.text.strip()

        thumb_el = item.find("thumbnail")
        if thumb_el is not None and (thumb_el.text or "").strip():
            return thumb_el.text.strip()

        return None

    return None


wingspan_image_url = fetch_bgg_image_url("266192")

print(wingspan_image_url)