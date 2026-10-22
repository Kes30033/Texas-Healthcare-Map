"""Map positions for street addresses, remembered by address in data/geocode/cache.json.

  python scripts/geocode.py ADDRESSES.csv [--retry]     (columns: street, city, zip, name)

First asks the U.S. Census batch geocoder; addresses it can't match go to OpenStreetMap Nominatim
(one request a second, as its usage policy asks). Both answers are cached, so reruns only look up
new addresses. Other scripts call lookup() directly.
"""
import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "geocode" / "cache.json"
CENSUS = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "Texas-Healthcare-Map/1.0 (github.com/Kes30033/Texas-Healthcare-Map)"
TEXAS = (25.8, 36.6, -106.7, -93.5)


def clean_street(street):
    """Drop suite, unit and building parts, which geocoders can't use ("100 Main St, Suite 2" -> "100 Main St")."""
    s = re.sub(r"^[:\s]+", "", street)
    s = re.sub(r"(?i)^(\d+)([A-Z]{3,})", r"\1 \2", s)                 # "4211NORTH JACKSON" -> "4211 NORTH JACKSON"
    s = re.sub(r"(?i)(?<=[A-Z])(STE|SUITE)\s*\d+.*$", "", s)           # "DATAPOINT DRSTE136" -> "DATAPOINT DR"
    s = re.sub(r"(?i)[,\s]+(suite|ste\.?|unit|bldg\.?|building|po box|rm\.?|room|level|lvl|#)(\s|\d|$).*$", "", s)
    s = re.sub(r"(?i)[,\s]+\d+(st|nd|rd|th)\s+floor.*$", "", s)
    s = re.sub(r"(?i)\bI[- ]?(\d+)\b", r"Interstate \1", s)            # "I-45" -> "Interstate 45"
    return s.strip(" ,-")


def key(street, city, zip_code):
    return re.sub(r"\s+", " ", f"{street}|{city}|{zip_code[:5]}".upper()).strip()


def load():
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def save(cache):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True), encoding="utf-8")


def in_texas(lat, lon):
    return TEXAS[0] < lat < TEXAS[1] and TEXAS[2] < lon < TEXAS[3]


def census_batch(items):
    """items: [(key, street, city, zip)] -> {key: {lat, lon, how}} for matches."""
    out = {}
    for i in range(0, len(items), 2000):
        buf = io.StringIO()
        w = csv.writer(buf)
        for n, (k, street, city, z) in enumerate(items[i:i + 2000]):
            w.writerow([i + n, street, city, "TX", z[:5]])
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"benchmark\"\r\n\r\nPublic_AR_Current\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"addressFile\"; filename=\"a.csv\"\r\n"
                f"Content-Type: text/csv\r\n\r\n{buf.getvalue()}\r\n--{boundary}--\r\n").encode()
        req = urllib.request.Request(CENSUS, data=body, headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=600) as r:
            text = r.read().decode("utf-8", "replace")
        for row in csv.reader(io.StringIO(text)):
            if len(row) >= 6 and row[2] == "Match":
                lon, lat = map(float, row[5].split(","))
                if in_texas(lat, lon):
                    out[items[int(row[0])][0]] = {"lat": round(lat, 6), "lon": round(lon, 6), "how": "census"}
        print(f"  census: {len(out)} matched of {min(i + 2000, len(items))}", flush=True)
    return out


def nominatim(street, city, z, name=None):
    tries = [{"street": street, "city": city, "state": "Texas", "postalcode": z[:5]},
             {"street": street, "city": city, "state": "Texas"}]
    if name:
        tries.append({"q": f"{name}, {city}, Texas"})
    for params in tries:
        params.update(format="json", limit=1, countrycodes="us")
        req = urllib.request.Request(NOMINATIM + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                hits = json.load(r)
        except Exception as e:
            print("  nominatim error", e)
            hits = []
        time.sleep(1.1)
        if hits:
            lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
            if in_texas(lat, lon):
                return {"lat": round(lat, 6), "lon": round(lon, 6), "how": "osm" if "q" not in params else "osm-name"}
    return None


def lookup(records, retry=False):
    """records: [(street, city, zip, name_or_None)] -> {key: {lat, lon, how} or {"how": "none"}}"""
    cache = load()
    if retry:   # addresses nobody could place last time get another try
        cache = {k: v for k, v in cache.items() if v["how"] != "none"}
    todo = {}
    for street, city, z, name in records:
        k = key(street, city, z)
        if k not in cache and k not in todo:
            todo[k] = (street, city, z, name)
    if todo:
        print(f"geocoding {len(todo)} new addresses")
        found = census_batch([(k, clean_street(v[0]), v[1], v[2]) for k, v in todo.items()])
        cache.update(found)
        save(cache)
        rest = [k for k in todo if k not in found]
        for n, k in enumerate(rest):
            street, city, z, name = todo[k]
            cache[k] = nominatim(clean_street(street), city, z, name) or {"how": "none"}
            if n % 20 == 19:
                save(cache)
                print(f"  osm: {n + 1}/{len(rest)}", flush=True)
        save(cache)
    return {key(s, c, z): cache[key(s, c, z)] for s, c, z, _ in records}


if __name__ == "__main__":
    rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
    res = lookup([(r["street"], r["city"], r["zip"], r.get("name")) for r in rows], retry="--retry" in sys.argv)
    from collections import Counter
    print(Counter(v["how"] for v in res.values()))
