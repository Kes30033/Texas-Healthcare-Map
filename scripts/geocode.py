"""Map positions for street addresses, remembered by address in data/geocode/cache.json.

  python scripts/geocode.py ADDRESSES.csv [--retry]     (columns: street, city, zip, name)

First asks the U.S. Census batch geocoder; addresses it can't match go to OpenStreetMap Nominatim
(one request a second, as its usage policy asks). Both answers are cached, so reruns only look up
new addresses. Other scripts call lookup() directly.

The Census geocoder answers "Non_Exact" when it had to bend the address to match, and sometimes it bends
it onto another street ("2000 S Mays" -> "2000 N Mays", "12838 Vista del Norte" -> "12838 Vista Haven").
Those answers are thrown out. Nominatim answers are marked "osm" only when OpenStreetMap has the building
or address point; when it only knows the street, the answer is marked "osm-street" and treated as approximate.

osm_address() asks Nominatim (then Photon, another OpenStreetMap search) for the building or address point of an
address even when the Census matched it (cached in data/geocode/osm_address.json). The map uses it for facilities, since the Census geocoder
estimates a position along the block, which can be a few hundred meters off on long blocks and frontage roads.
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
OSM_CACHE = ROOT / "data" / "geocode" / "osm_address.json"
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


DIRECTIONS = {"N": "N", "NORTH": "N", "S": "S", "SOUTH": "S", "E": "E", "EAST": "E", "W": "W", "WEST": "W",
              "NE": "NE", "NW": "NW", "SE": "SE", "SW": "SW"}
STREET_TYPES = {"ST", "STREET", "RD", "ROAD", "DR", "DRIVE", "BLVD", "BOULEVARD", "AVE", "AVENUE", "AV", "PKWY", "PARKWAY",
                "LN", "LANE", "HWY", "HIGHWAY", "FWY", "FREEWAY", "EXPY", "EXPRESSWAY", "EXPWY", "TRL", "TRAIL", "CIR",
                "CIRCLE", "CT", "COURT", "PL", "PLACE", "WAY", "LOOP", "XING", "CROSSING", "PLZ", "PLAZA", "TER", "TERRACE",
                "PASS", "PT", "POINT", "SQ", "ROW", "RUN", "PATH", "BND", "BEND", "SVC", "SERVICE", "FRONTAGE", "ACCESS",
                "BUS", "BUSINESS", "US", "STATE", "TX", "SH", "FM", "RR", "RM", "SPUR", "CO", "COUNTY", "I", "IH", "INTERSTATE"}
TYPE_SHORT = {"STREET": "ST", "ROAD": "RD", "DRIVE": "DR", "BOULEVARD": "BLVD", "AVENUE": "AVE", "AV": "AVE", "PARKWAY": "PKWY",
              "LANE": "LN", "TRAIL": "TRL", "CIRCLE": "CIR", "COURT": "CT", "PLACE": "PL", "CROSSING": "XING", "PLAZA": "PLZ",
              "HIGHWAY": "HWY", "FREEWAY": "FWY", "EXPY": "FWY", "EXPWY": "FWY", "EXPRESSWAY": "FWY"}
LOCAL_TYPES = {"ST", "RD", "DR", "BLVD", "AVE", "PKWY", "LN", "TRL", "CIR", "CT", "PL", "WAY", "LOOP", "XING", "PLZ", "HWY", "FWY"}


def street_parts(street):
    """'2000 South Mays Street, Suite 400' -> ('2000', {'S'}, ['MAYS'], {'ST'}, ['MAYS']).
    The last part is the street's own name: the words before its type ("Holcombe Blvd Main Building" -> HOLCOMBE)."""
    w = re.sub(r"[^A-Z0-9 ]", " ", clean_street(street.upper())).split()
    num = w.pop(0) if w and w[0].isdigit() else ""
    core = [x for x in w if x not in DIRECTIONS and x not in STREET_TYPES and (len(x) > 1 or x.isdigit())]   # not "1480-B"
    first_type = next((i for i, x in enumerate(w) if x in STREET_TYPES and i > 0), len(w))
    name = [x for x in w[:first_type] if x in core] or core
    return num, {DIRECTIONS[x] for x in w if x in DIRECTIONS}, core, {TYPE_SHORT.get(x, x) for x in w} & LOCAL_TYPES, name


def similar(a, b):
    """Same word give or take one typo or an abbreviation ('BISSONNNET' ~ 'BISSONNET', 'MEDI' ~ 'MEDICAL')."""
    if a == b or (len(a) > 3 and len(b) > 3 and (a.startswith(b) or b.startswith(a))):
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i + 1:] or a[i + 1:] == b[i:] or a[i:] == b[i + 1:]


def same_street(asked, matched, types=True):
    """Whether a geocoder's matched address is still the address that was asked for: same number, no clashing
    direction or street type (unless types=False), and the same street name (extra words after the street type are
    ignored)."""
    n1, d1, c1, t1, name1 = street_parts(asked)
    n2, d2, c2, t2, name2 = street_parts(matched)
    if (n1 and n2 and n1 != n2) or (d1 and d2 and d1 != d2) or (types and t1 and t2 and not t1 & t2):
        return False   # "N Loop 1604 W" isn't "N Loop 1604 E"
    if "".join(name1) == "".join(c2):   # "STONE HUE" ~ "STONEHUE"
        return True
    return all(any(similar(b, a) for a in c1) for b in c2) and all(any(similar(a, b) for b in c2) for a in name1)


def trusted(street, zip_code, match, matched):
    """Whether a Census answer can be used as is: an exact match, or a bent one that kept the street. In another ZIP
    code it also has to keep the street's directions ("6011 W Sam Houston Pkwy S" isn't "6011 Sam Houston Pkwy" across town)."""
    if match == "Exact":
        return True
    if not same_street(street, matched.split(",")[0]):
        return False
    same_zip = not zip_code or matched.rsplit(",", 1)[-1].strip() == zip_code[:5]
    return same_zip or street_parts(street)[1] == street_parts(matched.split(",")[0])[1]


def key(street, city, zip_code):
    return re.sub(r"\s+", " ", f"{street}|{city}|{zip_code[:5]}".upper()).strip()


def load(path=CACHE):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save(cache, path=CACHE):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=0, sort_keys=True), encoding="utf-8")


def in_texas(lat, lon):
    return TEXAS[0] < lat < TEXAS[1] and TEXAS[2] < lon < TEXAS[3]


def census_batch(items):
    """items: [(key, street, city, zip)] -> {key: {lat, lon, how, match, matched}} for matches. A "Non_Exact" match
    onto some other street comes back with how "census-loose"."""
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
                k, street, _, z = items[int(row[0])]
                ok = trusted(street, z, row[3], row[4])
                lon, lat = map(float, row[5].split(","))
                if in_texas(lat, lon):
                    out[k] = {"lat": round(lat, 6), "lon": round(lon, 6), "how": "census" if ok else "census-loose",
                              "match": row[3], "matched": row[4]}
        print(f"  census: {len(out)} matched of {min(i + 2000, len(items))}", flush=True)
    return out


def nominatim_search(params):
    params = dict(params, format="jsonv2", limit=1, countrycodes="us", addressdetails=1)
    req = urllib.request.Request(NOMINATIM + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            hits = json.load(r)
    except Exception as e:
        print("  nominatim error", e)
        hits = []
    time.sleep(1.1)
    return hits[0] if hits and in_texas(float(hits[0]["lat"]), float(hits[0]["lon"])) else None


def at_address(hit, street):
    """Whether a Nominatim hit is the building or address point itself, not just the street."""
    num = street_parts(street)[0]
    return bool(num) and hit.get("address", {}).get("house_number", "").split(";")[0].strip() == num


def nominatim(street, city, z, name=None):
    tries = [{"street": street, "city": city, "state": "Texas", "postalcode": z[:5]},
             {"street": street, "city": city, "state": "Texas"}]
    street_hit = None
    for params in tries:
        h = nominatim_search(params)
        if h and at_address(h, street):
            return {"lat": round(float(h["lat"]), 6), "lon": round(float(h["lon"]), 6), "how": "osm"}
        if h and h.get("category") == "highway" and not street_hit:
            street_hit = h
    if name:
        h = nominatim_search({"q": f"{name}, {city}, Texas"})
        if h and h.get("category") in ("amenity", "healthcare", "building", "office"):
            return {"lat": round(float(h["lat"]), 6), "lon": round(float(h["lon"]), 6), "how": "osm-name", "found": h.get("name", "")}
    if street_hit:   # only the street: somewhere along it
        return {"lat": round(float(street_hit["lat"]), 6), "lon": round(float(street_hit["lon"]), 6), "how": "osm-street"}
    return None


def lookup(records, retry=False):
    """records: [(street, city, zip, name_or_None)] -> {key: {lat, lon, how} or {"how": "none"}}.
    how: census, osm (building or address point), osm-name (found by name), and the approximate ones:
    census-loose (Census matched a similar street), osm-street (somewhere along the street)."""
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
        cache.update({k: v for k, v in found.items() if v["how"] == "census"})
        save(cache)
        rest = [k for k in todo if cache.get(k, {}).get("how") != "census"]
        for n, k in enumerate(rest):
            street, city, z, name = todo[k]
            hit = nominatim(clean_street(street), city, z, name)
            if not hit or hit["how"] == "osm-street":   # a Census match on a similar street beats the middle of the street
                hit = found.get(k) or hit
            cache[k] = hit or {"how": "none"}
            if n % 20 == 19:
                save(cache)
                print(f"  osm: {n + 1}/{len(rest)}", flush=True)
        save(cache)
    return {key(s, c, z): cache[key(s, c, z)] for s, c, z, _ in records}


PHOTON_TRY = "nominatim, photon (any street type)"   # what a "not found" answer has tried; older answers get retried


def town_key(name):
    return re.sub(r"[^a-z]", "", (name or "").lower().replace("saint ", "st "))


def photon(street, city, z):
    """Photon (komoot's OpenStreetMap search) finds some address points Nominatim's structured search misses.
    Only a hit with the same house number, the same street name and the same town or ZIP code counts; the street
    type may differ, since CMS addresses often have it wrong ("1307 Cleveland Street" is on Cleveland Avenue)."""
    url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode({"q": f"{street}, {city}, Texas", "limit": 5})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
            feats = json.load(r).get("features", [])
    except Exception as e:
        print("  photon error", e)
        feats = []
    time.sleep(1.1)
    num = street_parts(street)[0]
    for f in feats:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        if (num and p.get("housenumber", "").split(";")[0] == num and same_street(street, f"{num} {p.get('street', '')}", types=False)
                and (town_key(p.get("city")) == town_key(city) or p.get("postcode", "")[:5] == z[:5]) and in_texas(lat, lon)):
            return {"lat": round(lat, 6), "lon": round(lon, 6), "src": "photon",
                    "found": " ".join(str(p.get(x, "")) for x in ("name", "housenumber", "street", "city", "postcode")).strip()[:100]}
    return None


def osm_address(records):
    """records: [(street, city, zip)] -> {key: {lat, lon} or {}}: OpenStreetMap's building or address point,
    from Nominatim, or else Photon."""
    cache = load(OSM_CACHE)
    todo = {key(s, c, z): (s, c, z) for s, c, z in records
            if key(s, c, z) not in cache or ("lat" not in cache[key(s, c, z)] and cache[key(s, c, z)].get("tried") != PHOTON_TRY)}
    if todo:
        print(f"asking OpenStreetMap for {len(todo)} building positions (about {len(todo) * 2.3 / 60:.0f} min)", flush=True)
    for n, (k, (street, city, z)) in enumerate(todo.items()):
        street = clean_street(street)
        if k not in cache:
            for params in ({"street": street, "city": city, "state": "Texas", "postalcode": z[:5]},
                           {"street": street, "city": city, "state": "Texas"}):
                h = nominatim_search(params)
                if h and at_address(h, street):
                    cache[k] = {"lat": round(float(h["lat"]), 6), "lon": round(float(h["lon"]), 6),
                                "found": h.get("display_name", "")[:100]}
                    break
        if "lat" not in cache.get(k, {}):
            cache[k] = photon(street, city, z) or {"tried": PHOTON_TRY}
        if n % 20 == 19:
            save(cache, OSM_CACHE)
            print(f"  {n + 1}/{len(todo)}", flush=True)
    save(cache, OSM_CACHE)
    return {key(s, c, z): cache[key(s, c, z)] for s, c, z in records}


if __name__ == "__main__":
    rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
    res = lookup([(r["street"], r["city"], r["zip"], r.get("name")) for r in rows], retry="--retry" in sys.argv)
    from collections import Counter
    print(Counter(v["how"] for v in res.values()))
