"""Turn TABS filings and researched news reports into the map's sites (facilities and new-facility
locations) and their construction projects.

  python scripts/build_projects.py [--retry-geocode]    (--retry-geocode: try again on addresses no geocoder placed)

Reads  data/facilities.csv, data/tabs/search/*.jsonl, data/tabs/details/*.json, data/research/news_projects.csv
Writes data/sites.json      everything the website needs
       data/projects.csv    one row per project, for the spreadsheet
       data/review.csv      filings left off the map, with the reason, for spot checks

How a filing is classified:
  1. Active: not closed or inspected, and the estimated completion is no more than 150 days past.
  2. Linked to a facility when its address is the facility's street address, or it is within 600 m and
     shares a distinctive name (Hendrick, Methodist...), or it is within 150 m of a hospital and is
     medical work. Surgery centers also need surgery-related wording, since they share buildings.
  3. Not linked: kept as a NEW hospital or surgery center only when the filing describes one, and
     dropped when it is a psychiatric, rehab or long-term care hospital, a clinic, an animal hospital...
  4. Kind: new facility; expansion (new construction or an addition at a facility); renovation.
  5. Stage: "filed, not started" when the estimated start date is still ahead, otherwise "under construction".
"""
import csv
import datetime
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geocode                                    # noqa: E402
from tabs_candidates import STATUS, WORK, active, load_search, relevant   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TODAY = datetime.date.today().isoformat()
HOSPITAL_TYPES = {"Acute Care Hospital", "Critical Access Hospital", "Children's Hospital", "VA Hospital", "Military Hospital"}

STOP = set("""hospital hospitals medical med center centre ctr health healthcare the of at and texas tx regional surgery
surgical surgicenter ascs asc campus building bldg renovation renovations remodel new phase ph floor level suite ste mob
tower expansion addition project llc inc lp pllc pa ltd system systems care clinic services service unit room rooms
north south east west n s e w first second third 1st 2nd 3rd 4th 5th main dept department upgrade replacement
improvements improvement interior exterior finish out build buildout plaza pavilion institute associates group
partners community general memorial county city emergency er""".split())
HOSP_WORDS = re.compile(r"\bhospital\b|emergency hospital|neighborhood hospital|micro.?hospital|patient (care )?tower|"
                        r"bed tower|inpatient|medical center|\bmed(ical)? ctr\b", re.I)
ASC_WORDS = re.compile(r"\bASCs?\b|ambulatory surg|surgery cent|surgical cent|surgicent|surgery ctr|surgical ctr|"
                       r"endoscopy (center|suite)|surgical suite|surgical hospital|\bsurgery\b|\bsurgical\b|"
                       r"operating rooms?|\bOR suite", re.I)
MEDICAL_WORK = re.compile(r"hospital|surg|patient|\bN?ICU\b|\bPICU\b|\bCVICU\b|\bOR\b|operating|emergency|\bE\.?D\.?\b|"
                          r"imaging|radiolog|\bMRI\b|\bCT\b|cath|pharmacy|lab|sterile|\bSPD\b|nurs|L&D|labor|maternity|"
                          r"neonat|women|pediatric|oncolog|cancer|infusion|endoscop|dialysis|tower|bed|unit|inpatient|"
                          r"trauma|cardi|heart|ortho|spine|neuro|interventional|procedure|med|clinic|kitchen|cafeteria|"
                          r"central (energy|plant|utility)|\bCUP\b|chiller|generator|elevator|parking|lobby|entrance|"
                          r"canopy|roof|restroom|corridor|nurse|physician|sleep|wound|rehab|therapy|morgue|chapel", re.I)
NOT_ACUTE = re.compile(r"animal|veterinar|\bvet\b|equine|psychiatr|behavioral|mental health|state hospital|state supported|"
                       r"rehabilitation hospital|rehab hospital|inpatient rehab|\bIRF\b|long.?term acute|\bLTAC|"
                       r"kindred|select specialty|vibra|cornerstone specialty|post.?acute|encompass health|nobis|"
                       r"pam (health|rehab|specialty)|lifepoint rehab|ernest health|hospice|nursing (home|facility)|"
                       r"skilled nursing|senior living|assisted living|memory care|dental|\boral\b|maxillofacial|orthodont|"
                       r"hospital (dr|drive|blvd|boulevard|pkwy|parkway|st|street|rd|road|ave|avenue|way|lane)\b|"
                       r"\bhospital district (office|admin)|county jail|detention|correctional|hotel|"
                       r"(homewood|home2|staybridge|towneplace|springhill) suites|\binn\b|apartment|residences|"
                       r"parking garage only|turtle|wildlife|\bzoo\b|aquarium|\bblood\b|hospital council|association|"
                       r"lasik|geriatric", re.I)
NEW_FACILITY_WORDS = re.compile(r"\bnew\b|ground.?up|build.?out|finish.?out|conversion|convert|shell|"
                                r"tenant (improvement|finish)|white.?box|interior finish|\bTI\b|\bTFO\b", re.I)
OFFICE_ONLY = re.compile(r"\bMOB\b|medical office|office building|professional (building|office)|physicians? (office|building)|"
                         r"\bclinic\b|urgent care|freestanding (emergency|er|ed)\b|\bFSED\b|\bFSER\b|\boffices?\b|"
                         r"sports medicine|\bSMR\b|pediatrics", re.I)
# Work that is clearly the hospital's own, for linking a filing to a hospital nearby without a name match
HOSPITAL_CORE = re.compile(r"hospital|patient|inpatient|\bN?ICU\b|\bPICU\b|\bCVICU\b|surg|emergency|\bE\.?D\.?\b|imaging|"
                           r"radiolog|\bMRI\b|\bCT\b|cath|\bOR\b|\bORs\b|operating|nurs|L&D|labor and|maternity|neonat|"
                           r"\bbeds?\b|tower|pharmacy|laborator|\blab\b|oncolog|cancer|infusion|endoscop|dialysis|"
                           r"trauma|sterile|\bSPD\b|kitchen|dietary|central (energy|plant|utility)|\bCUP\b|chiller|"
                           r"generator|elevator|parking|garage|helipad|morgue|chapel|lobby|birth|women", re.I)
CLINICAL = re.compile(r"hospital|surg|patient|\bN?ICU\b|\bPICU\b|emergency|\bE\.?D\.?\b|imaging|\bMRI\b|\bCT\b|cath|"
                      r"\bOR\b|operating|nurs|L&D|labor|oncolog|cancer|infusion|endoscop|clinic|medical|health|"
                      r"pharmacy|tower|bed\b|unit\b", re.I)
NONCLINICAL = re.compile(r"research|bioscience|college of medicine|school of (medicine|nursing)|academic|classroom|"
                         r"\beducation|student|\bISD\b|elementary|junior high|high school|car wash|travel center|"
                         r"data center|auto parts|\btarget\b|meeting hall|\bpark\b(?! (plaza|place|blvd))|fire station|"
                         r"\bcourt\b|\blaw\b|\bnyse\b|capital|office (for|of) (a|the)? ?(law|engineering)|\bcity of\b|"
                         r"\bCOSA\b|\bHHD\b|emergency operations|la villita|plaza juarez|\bdeli\b|chick-fil-a|\bCFA\b|"
                         r"starbucks|food hall|biochemistry|dermatology|\bderm\b|medical school|transit (center|station)|"
                         r"\bMETRO (TMC|transit|bus|rail)\b|medical examiner|forensic|"
                         r"fume hood|research (bldg|building|lab)|south campus research|\b\dSCR|shade house|"
                         r"farm pavilion", re.I)
# A filing that isn't at a known facility counts as a NEW hospital or surgery center only with wording like this
STRONG_ASC = re.compile(r"\bASCs?\b|ambulatory surg|surgery cent|surgical cent|surgicent|surgery ctr|surgical ctr|"
                        r"endoscopy cent|surgical suites?\b", re.I)
STRONG_HOSPITAL = re.compile(r"new (\w+ )?hospital|micro.?hospital|neighborhood hospital|emergency hospital|"
                             r"replacement hospital|surgical hospital|small.?format hospital|acute care hospital|"
                             r"\bhospital\b(?! (district|council|drive|dr|blvd|parkway|pkwy|road|rd|street|st)\b)", re.I)
# ...and not when it reads like work on an existing building that we couldn't match to a facility
EXISTING_WORK = re.compile(r"expansion|addition|renovat|remodel|refresh|upgrade|replace(?!ment hospital)|moderniz|"
                           r"improvement|repair|\blevel \d|\d(st|nd|rd|th) floor|floor \d|parking|garage|\broof|hvac|"
                           r"elevator|generator|chiller|kitchen|lobby|backfill|equipment|\bunit\b|\bICU\b|\bPICU\b|"
                           r"\bNICU\b|\bMRI\b|\bCT\b|cath lab|pharmacy|restroom|tower", re.I)


ALIASES = {"mdacc": "anderson", "utmda": "anderson", "mda": "anderson", "mdanderson": "anderson", "tch": "childrens",
           "utsw": "southwestern", "bumc": "baylor", "bsw": "baylor", "bswh": "baylor", "thr": "texas",
           "hmh": "methodist", "mhwt": "methodist", "hmwb": "methodist", "hmsl": "methodist", "hmch": "methodist",
           "hmtw": "methodist", "hmtwh": "methodist", "hmclh": "methodist", "hmb": "methodist", "mhhs": "hermann",
           "mhmc": "hermann", "ctmf": "christus", "jps": "jps", "umc": "umc", "children's": "childrens"}


def tokens(*texts):
    words = {w for t in texts for w in re.findall(r"[a-z][a-z'&]+", (t or "").lower().replace("’", "'"))
             if w.strip("'") not in STOP and len(w) > 2}
    return words | {ALIASES[w] for w in words if w in ALIASES}   # "MDACC" also counts as "Anderson"


def town(name):
    """One spelling per town: "Mc Kinney" = "McKinney", "Ft Worth" = "Fort Worth"."""
    s = re.sub(r"\bst\.? ", "saint ", re.sub(r"\bft\.? ", "fort ", (name or "").lower()))
    return re.sub(r"[^a-z]", "", s)


def initials(name):
    """{"umc"} for "University Medical Center": filings often use a hospital's initials."""
    words = [w for w in re.findall(r"[a-z]+", (name or "").lower()) if w not in ("of", "the", "and", "at")]
    return {"".join(w[0] for w in words)} if len(words) >= 3 else set()


def name_score(a, b):
    """Share of the shorter name's distinctive words found in the other name."""
    if not a or not b:
        return 0
    return len(a & b) / min(len(a), len(b))


def dist_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    x = (lo2 - lo1) * math.cos((la1 + la2) / 2)
    return 6371000 * math.hypot(x, la2 - la1)


def street_parts(street):
    """("1900", {"pine"}) from "1900 Pine Street, Suite 2"."""
    s = geocode.clean_street(street or "").lower()
    m = re.match(r"\s*(\d+)\s*(.*)", s)
    if not m:
        return None, set()
    words = set(re.findall(r"[a-z0-9]+", m[2])) - {"n", "s", "e", "w", "north", "south", "east", "west", "st", "street",
                                                   "rd", "road", "dr", "drive", "ave", "avenue", "blvd", "boulevard",
                                                   "pkwy", "parkway", "hwy", "highway", "ln", "lane", "way", "fwy",
                                                   "freeway", "expy", "expressway", "loop", "ste", "suite", "ct", "cir"}
    return m[1], words


def same_address(fac, street, slack=0):
    """Same street number (within slack: hospital campuses span several numbers) on the same street."""
    n1, w1 = street_parts(fac["Street Address"])
    n2, w2 = street_parts(street)
    same_street = bool(w1 & w2) or (not slack and (not w1 or not w2))
    return bool(n1) and bool(n2) and abs(int(n1) - int(n2)) <= slack and same_street


def iso(d):
    """'11/2/2026' or '2026-11-02T00:00:00' -> '2026-11-02'."""
    d = (d or "").strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", d)
    return f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}" if m else d[:10]


def money(v):
    v = re.sub(r"[^\d.]", "", str(v or ""))
    return int(float(v)) if v else 0


def nice(name):
    name = re.sub(r"\s+", " ", (name or "").strip())
    return name.title().replace("'S ", "'s ") if name.isupper() and len(name) > 4 else name


SYSTEM_WORDS = {"baylor", "scott", "white", "texas", "health", "christus", "methodist", "memorial", "hermann", "medical",
                "center", "hospital", "regional", "hca", "houston", "healthcare", "saint", "the", "campus", "system",
                "university", "baptist", "general", "county", "community", "district"}


def name_words(s):
    return {w for w in re.findall(r"[a-z]+", re.sub(r"\bst\b\.?", "saint", s.lower())) if len(w) > 2}


def osm_position(f, osm):
    """A hospital's OpenStreetMap position, when OSM has the same hospital (same name and street number, or the
    same distinctive name in the same city). Address geocoders sometimes land kilometers away."""
    ft = name_words(f["Name"])
    num = (re.findall(r"\d+", f["Street Address"]) or [""])[0]
    best = None
    for o in osm:
        d = dist_m((f["lat"], f["lng"]), (o["lat"], o["lng"]))
        if d > 60000:
            continue
        ot = name_words(o["name"])
        share = len(ft & ot) / max(1, min(len(ft), len(ot)))
        same_num = bool(num) and o["addr"].split(" ")[0] == num
        same_city = town(o["city"]) == town(f["City"])
        distinctive = (ft & ot) - SYSTEM_WORDS - name_words(f["City"])   # not just "Texas Health" or "Lubbock"
        if (same_num and share >= 0.4) or (same_city and share >= 0.99 and distinctive):
            if not best or d < best[0]:
                best = (d, o)
    return best


POSITION = {"pinned": "Pinned by hand or from OpenStreetMap", "building": "Building (OpenStreetMap)",
            "osm-hospital": "Hospital (OpenStreetMap)", "census": "Street address (U.S. Census)",
            "osm": "Street address (OpenStreetMap)", "osm-name": "Found by name (OpenStreetMap)",
            "census-loose": "Approximate: the address only matched a similar street nearby",
            "osm-street": "Approximate: placed on the street, not at the building",
            "zip": "Approximate: the address couldn't be matched, so the dot is at the center of its ZIP code",
            "news": "Address in news reports", "news-area": "Approximate: the area named in news reports"}
APPROX = {"census-loose", "osm-street", "zip", "news-area"}


def county_finder():
    """(lat, lng, county) -> the county the point is in, when it's clearly inside another county than the one given
    (CMS sometimes lists a city's main county, or a wrong one), or the given county otherwise."""
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree
    feats = json.loads((ROOT / "data/basemap/basemap.json").read_text(encoding="utf-8"))["counties"]
    names, shapes = [f["properties"]["name"] for f in feats], [shape(f["geometry"]) for f in feats]
    tree, by_name = STRtree(shapes), dict(zip(names, shapes))

    def find(lat, lng, given):
        pt = Point(lng, lat)
        inside = [names[i] for i in tree.query(pt) if shapes[i].contains(pt)]
        if not inside or inside[0] == given:
            return given
        if given in by_name and by_name[given].distance(pt) < 0.003:   # within ~300 m: the map's county lines are simplified
            return given
        return inside[0]
    return find


def load_facilities():
    """Facilities with map positions, best first: a pinned position (campuses, data/facility_fixes.csv), the
    OpenStreetMap building at the address, the address geocoders, then the ZIP code's center. Hospitals whose
    OpenStreetMap hospital (same name and street number) is more than 150 m from that go to the hospital."""
    zips = json.load(open(ROOT / "data/geocode/zip_centers.json"))
    osm = list(json.loads((ROOT / "data/osm/hospitals.json").read_text(encoding="utf-8")).values())
    rows = list(csv.DictReader(open(ROOT / "data/facilities.csv", encoding="utf-8")))
    need = [r for r in rows if not r["Latitude"]]
    pos = geocode.lookup([(r["Street Address"], r["City"], r["ZIP"], r["Name"]) for r in need])
    bld = geocode.osm_address([(r["Street Address"], r["City"], r["ZIP"]) for r in need])
    county = county_finder()
    out, how = [], Counter()
    for r in rows:
        k = geocode.key(r["Street Address"], r["City"], r["ZIP"])
        g, b = pos.get(k, {}), bld.get(k, {})
        if r["Latitude"]:
            r["lat"], r["lng"], r["how"] = float(r["Latitude"]), float(r["Longitude"]), "pinned"
        elif "lat" in b:
            r["lat"], r["lng"], r["how"] = b["lat"], b["lon"], "building"
        elif "lat" in g:
            r["lat"], r["lng"], r["how"] = g["lat"], g["lon"], g["how"]
        elif r["ZIP"] in zips:
            (r["lat"], r["lng"]), r["how"] = zips[r["ZIP"]], "zip"
        else:
            print("  no position for", r["Name"])
            continue
        r["hospital"] = r["Type"] in HOSPITAL_TYPES
        if r["hospital"] and r["how"] != "pinned":
            hit = osm_position(r, osm)
            if hit and hit[0] > 150:
                r["lat"], r["lng"], r["how"] = hit[1]["lat"], hit[1]["lng"], "osm-hospital"
        if r["how"] in ("osm-name", "osm-street", "census-loose") and r["ZIP"] in zips and (
                dist_m((r["lat"], r["lng"]), zips[r["ZIP"]]) > 30000):
            (r["lat"], r["lng"]), r["how"] = zips[r["ZIP"]], "zip"   # geocoder landed far outside the ZIP code
        r["approx"], r["pos"] = r["how"] in APPROX, POSITION[r["how"]]
        if r["how"] != "zip":
            r["County"] = county(r["lat"], r["lng"], r["County"])
        r["tok"] = tokens(r["Name"])
        how[r["how"]] += 1
        out.append(r)
    print("  facility positions:", dict(how))
    return out


def load_details(nums):
    d = {}
    for n in nums:
        f = ROOT / "data/tabs/details" / f"{n}.json"
        if f.exists():
            d[n] = json.loads(f.read_text(encoding="utf-8"))
    return d


def split_address(a):
    """'1820 SSW Loop 323, Tyler, TX 75701' -> ('1820 SSW Loop 323', 'Tyler', '75701')."""
    m = re.match(r"(.*?),\s*([^,]+?),?\s+(?:TX|Texas)\.?,?\s*(\d{5})?", a or "", re.I)   # first one if repeated
    return (m[1].strip(), m[2].strip(), m[3] or "") if m else ((a or "").strip(), "", "")


def main():
    facilities = load_facilities()
    fac_by_id = {f["Facility ID"]: f for f in facilities}
    df = Counter(t for f in facilities for t in f["tok"])   # how many facility names use each word
    # town names can't link a filing to a facility on their own ("Texarkana", "Pampa"), even across towns
    place_words = {w for c in json.load(open(ROOT / "data/tabs/cities.json")).values() for w in tokens(c)}
    place_words -= {t for f in facilities for t in f["tok"] if df[t] <= 3} - {w for f in facilities for w in tokens(f["City"])}
    search = load_search()
    nums = sorted(n for n, r in search.items() if active(r) and relevant(r))
    details = load_details(nums)
    print(f"{len(facilities)} facilities; {len(nums)} active filings, {len(details)} with details")

    # positions for every filing address
    recs = []
    for n in nums:
        if n in details:
            street, city, z = split_address(details[n].get("Location Address"))
            recs.append((street, city, z, None))
    pos = geocode.lookup(recs, retry="--retry-geocode" in sys.argv)
    zips = json.load(open(ROOT / "data/geocode/zip_centers.json"))
    news = load_news()
    forced = {num: row for row in news for num in row["tabs"].split()}   # filings a news report identifies

    projects, review = [], []
    for n in nums:
        r, d = search[n], details.get(n)
        if not d:
            review.append((n, r["ProjectName"], "no detail page yet"))
            continue
        street, city, z = split_address(d.get("Location Address"))
        g = pos.get(geocode.key(street, city, z), {})
        how = g["how"] if "lat" in g else "zip"
        ll = (g["lat"], g["lon"]) if "lat" in g else (tuple(zips[z]) if z in zips else None)
        approx = how in APPROX or ll is None
        text = " | ".join([r["ProjectName"], r["FacilityName"], d.get("Scope of Work", "")])
        title = f'{r["ProjectName"]} {r["FacilityName"]}'
        ptok = tokens(r["ProjectName"], r["FacilityName"], d.get("Owner Name"), d.get("Tenant Name"))
        p = {
            "num": n, "name": nice(r["ProjectName"]), "facility_name": nice(r["FacilityName"]),
            "scope": re.sub(r"\s+", " ", d.get("Scope of Work", "")).strip(),
            "cost": int(r.get("EstimatedCost") or 0) or money(d.get("Estimated Cost")),
            "start": iso(r.get("EstimatedStartDate") or d.get("Start Date")),
            "end": iso(r.get("EstimatedEndDate") or d.get("Completion Date")),
            "reg": iso(d.get("Registration Date") or r["ProjectCreatedOn"]),
            "status": STATUS.get(r["ProjectStatus"], ""), "work": WORK.get(r["TypeOfWork"], ""),
            "work_code": r["TypeOfWork"],
            "sqft": money((d.get("Square Footage") or "").split("ft")[0]),   # "60,000 ft 2" (ft²); "1" means not given
            "owner": d.get("Owner Name", ""), "tenant": d.get("Tenant Name", ""),
            "designer": d.get("Design Firm Name", ""), "addr": d.get("Location Address", ""),
            "street": street, "city": city, "zip": z, "ll": ll, "approx": approx, "how": how, "news": [], "builder": "",
            "opens": "",
        }

        # ---- link to a facility ----
        # Shared words don't count when they're just the place both are in ("Pampa", "Midland")
        own = lambda f: tokens(f["City"], f["County"], city)
        match = lambda f: name_score(f["tok"] - own(f), ptok - own(f))
        best, why = None, ""
        addr_ids = [q for q in r["queries"] if ":" not in q]   # found by searching a facility's street address
        same_town = [f for f in facilities if town(f["City"]) == town(city)] if city else []
        # a NEW surgery center going into a building that already has one isn't work at the existing one
        new_asc = re.search(r"new (\w+ )?(ambulatory surg|surgery cent|surgical cent|ASC)|(build.?out|finish.?out) (of|for) "
                            r"(a |an )?(new )?(ambulatory|surgery|surgical|ASC)", text, re.I)
        # a surgery center's building has other tenants ("Shady Grove Fertility" in the Museo building, home of
        # Museo ASC): the filing's name, building, owner or tenant has to be about surgery (its scope isn't enough)
        asc_ok = lambda f: bool(ASC_WORDS.search(f'{title} {d.get("Owner Name") or ""} {d.get("Tenant Name") or ""}'))
        at_address = [f for f in {f["Facility ID"]: f for f in [fac_by_id[q] for q in addr_ids if q in fac_by_id] + same_town}.values()
                      if same_address(f, street) and town(f["City"]) == town(city) and (f["hospital"] or asc_ok(f))
                      and not (new_asc and not f["hospital"] and name_score(f["tok"], ptok) < 0.5)]
        if at_address:   # several surgery centers can share a building: the one the filing names
            best, why = max(at_address, key=lambda f: (name_score(f["tok"], ptok), f["hospital"])), "same address"
        # who the filing is for: a hospital's neighbor only counts as its project when it's the hospital's own
        org_text = " ".join(x or "" for x in (d.get("Owner Name"), d.get("Tenant Name"), r["FacilityName"], r["ProjectName"]))
        org, org_plain = tokens(org_text), re.sub(r"[^a-z0-9 ]", "", org_text.lower())
        # the hospital's whole name, all its name words, its initials or a distinctive word of it (not just its town)
        affiliated = lambda f: (not (d.get("Owner Name") or d.get("Tenant Name"))
                                or re.sub(r"[^a-z0-9 ]", "", f["Name"].lower()) in org_plain
                                or (f["tok"] and f["tok"] <= org)
                                or bool(((f["tok"] - tokens(f["City"])) | initials(f["Name"])) & org))
        near = sorted(((dist_m(ll, (f["lat"], f["lng"])), f) for f in facilities), key=lambda x: x[0]) if ll else []
        if not best:   # the same name within 600 m, or a filing that says it's at the hospital when its address can't be placed
            at_hospital = p["how"] == "zip" and re.search(r"\bhospital\b", title, re.I)
            scored = [(match(f), -dd, f) for dd, f in near if dd <= 600 or (
                at_hospital and f["hospital"] and town(f["City"]) == town(city) and dd <= 5000)]
            scored = [s for s in scored if s[0] >= 0.5]
            if scored:
                sc, nd, f = max(scored, key=lambda s: (s[0], s[1]))
                if f["hospital"] or asc_ok(f):
                    best, why = f, f"same name, {-nd:.0f} m away" if -nd <= 600 else "same name and town (address not placed)"
        hospital_work = HOSPITAL_CORE.search(title) or (HOSPITAL_CORE.search(p["scope"]) and not OFFICE_ONLY.search(title))
        nearby = [f for dd, f in near if dd <= 3000] if ll else [f for f in facilities if town(f["City"]) == town(city)]
        names_other = any(f["hospital"] and match(f) >= 0.5 for f in nearby)   # the filing names a hospital
        if not best and hospital_work and not names_other and not NOT_ACUTE.search(title) and not new_asc:
            # a hospital campus: same street and a nearby street number, in the same town or within 2 km
            block = [f for f in facilities if f["hospital"] and same_address(f, street, slack=300) and affiliated(f) and (
                town(f["City"]) == town(city) or (ll and dist_m(ll, (f["lat"], f["lng"])) <= 2000))]
            if block:
                num = int(street_parts(street)[0])
                best = min(block, key=lambda f: abs(int(street_parts(f["Street Address"])[0]) - num))
                why = "same street address block"
            for dd, f in near if not best and HOSPITAL_CORE.search(title) else []:
                if dd > 250:
                    break
                if f["hospital"] and affiliated(f):
                    best, why = f, f"{dd:.0f} m from the hospital"
                    break
        if not best and ll:
            if not best and CLINICAL.search(title):   # a rare name nearby: "Huguley", "Driscoll"
                # a facility named for its street ("Fannin Surgicare") doesn't share a name with everything on that street
                rare = {t for t in tokens(r["ProjectName"], r["FacilityName"]) - tokens(city)
                        if len(t) >= 4 and t not in SYSTEM_WORDS and t not in place_words and 0 < df.get(t, 0) <= 3}
                cands = [(dist_m(ll, (f["lat"], f["lng"])), f) for f in facilities
                         if rare & (f["tok"] - tokens(f["Street Address"])) and (f["hospital"] or asc_ok(f))]
                cands = [c for c in cands if c[0] <= 800]
                if cands:
                    dd, f = min(cands, key=lambda c: c[0])
                    best, why = f, f"same name ({', '.join(sorted(rare & f['tok']))}), {dd:.0f} m away"
        if best and NOT_ACUTE.search(title) and not name_score(best["tok"], ptok) >= 0.5:
            best = None   # e.g. a rehab hospital or a dental office next door
        if NONCLINICAL.search(title) and not forced.get(n):
            review.append((n, r["ProjectName"], "research, academic or non-clinical building"))
            continue
        row = forced.get(n)
        if row and row["stage"] == "skip":   # news reports say the project stopped, though the filing is still open
            review.append((n, r["ProjectName"], "stopped, per news reports: " + row["summary"]))
            continue
        if row:   # a news report says what this filing is
            p["group"] = row["key"]
            if row["facility_id"] in fac_by_id:
                best, why = fac_by_id[row["facility_id"]], "news report"
            elif row["kind"] == "new":
                best = None   # a new hospital going up beside an existing one, e.g. the Dallas pediatric campus

        # ---- kind ----
        if row and not best and row["kind"] == "new" and ll:
            p["kind"], p["new_type"] = "new", row["type"]
        elif best:
            p["facility"] = best["Facility ID"]
            p["why"] = why
            p["kind"] = "ren" if r["TypeOfWork"] in (9002, 9004) else "exp"
        else:
            asc = STRONG_ASC.search(title) or STRONG_ASC.search(p["scope"])
            hosp = STRONG_HOSPITAL.search(title) or re.search(r"new (\w+ )?hospital", p["scope"], re.I)
            new_words = re.search(r"new (\w+ )?(hospital|surgery|surgical|ambulatory|ASC)|micro.?hospital|"
                                  r"neighborhood hospital|emergency hospital|replacement hospital|small.?format hospital",
                                  text, re.I)
            why_not = (
                "not a hospital or surgery center" if NOT_ACUTE.search(title) or not (hosp or asc) else
                "medical office or clinic, not a hospital or surgery center"
                if OFFICE_ONLY.search(title) and not STRONG_ASC.search(title) and not new_words else
                "addition at a hospital or surgery center not in the lists" if r["TypeOfWork"] == 9003 else
                "work at an existing building that isn't in the lists or couldn't be matched"
                if EXISTING_WORK.search(title) and not new_words else
                "renovation at a hospital or surgery center not in the lists"
                if r["TypeOfWork"] in (9002, 9004) and not (new_words or (asc and NEW_FACILITY_WORDS.search(text))) else
                "no usable address" if not ll else "")
            if why_not:
                review.append((n, r["ProjectName"], why_not))
                continue
            p["kind"], p["new_type"] = "new", "asc" if STRONG_ASC.search(r["ProjectName"]) or not hosp else "hosp"

        # ---- stage ----
        p["stage"] = "filed" if p["start"] and p["start"] > TODAY else "uc"
        projects.append(p)

    projects = drop_duplicates(projects, review)
    for p in projects:
        if p["sqft"] <= 1:
            p["sqft"] = 0
    keep_groups_together(projects)
    attach_news(projects, news, facilities, review)

    # ---- sites ----
    county = county_finder()
    sites, site_of_fac = [], {}
    for f in facilities:
        site_of_fac[f["Facility ID"]] = len(sites)
        sites.append({"k": 0, "id": f["Facility ID"], "n": f["Name"], "type": f["Type"], "lat": f["lat"], "lng": f["lng"],
                      "approx": f["approx"], "addr": f["Street Address"], "city": f["City"], "zip": f["ZIP"],
                      "county": f["County"], "phone": f["Phone"], "beds": f["Beds"], "ors": f["Operating Rooms"],
                      "own": f["Ownership"], "spec": f["Surgery Specialties"], "since": f["Medicare Since"],
                      "note": f.get("Note", ""), "pos": f["pos"], "pj": []})
    new_sites = []
    for i, p in sorted(enumerate(projects), key=lambda x: -x[1]["cost"]):
        if p["kind"] != "new":
            sites[site_of_fac[p["facility"]]]["pj"].append(i)
            continue
        ptok = tokens(p["name"], p["facility_name"], p["owner"])
        home = None
        for s in new_sites:
            if p.get("group") or s["group"]:   # filings a news report ties together share one site
                if p.get("group") == s["group"]:
                    home = s
                    break
                continue
            dd = dist_m(p["ll"], (s["lat"], s["lng"]))
            if dd <= 60 or (dd <= 400 and name_score(s["tok"], ptok) >= 0.5):
                home = s
                break
        if not home:
            home = {"k": 1, "id": "", "n": site_name(p), "lat": p["ll"][0], "lng": p["ll"][1],
                    "approx": p["approx"], "addr": p["street"], "city": p["city"], "zip": p["zip"],
                    "county": county(p["ll"][0], p["ll"][1], ""), "pos": POSITION.get(p["how"], "Address on the state filing"),
                    "pj": [], "tok": ptok, "types": set(), "group": p.get("group")}
            new_sites.append(home)
        home["pj"].append(i)
        home["types"].add(p["new_type"])
    for s in new_sites:
        s["type"] = "New hospital" if "hosp" in s["types"] else "New surgery center"
        del s["tok"], s["types"], s["group"]
        sites.append(s)
    for s in sites:   # new sites are also known by the names and owners on their filings
        extra = [] if s["k"] == 0 else [x for j in s["pj"] for x in (projects[j]["facility_name"], projects[j]["owner"])]
        s["sys"] = health_systems(" | ".join([s["n"], s.get("note", ""), *extra]), s["city"], s["type"])

    write(sites, projects, review)


SA_AREA = {"san antonio", "live oak", "jourdanton", "boerne", "fredericksburg", "balcones heights", "schertz", "selma",
           "new braunfels", "converse", "helotes", "universal city"}
HOUSTON_AREA = {"houston", "sugar land", "katy", "cypress", "baytown", "nassau bay", "the woodlands", "webster", "pearland",
                "spring", "tomball", "conroe", "humble", "kingwood", "bellaire", "pasadena", "league city", "texas city"}
SYSTEM_RULES = [   # (health system, pattern on the facility's name and notes, towns it applies in or None)
    ("CommonSpirit Health (St. Luke's Health, CHI St. Joseph)",
     r"st\.? luke'?s(?! baptist)|\bchi st|st\.? joseph health|commonspirit|baylor st\.? luke|baylor college of medicine", None),
    ("Baylor Scott & White Health", r"baylor scott|scott (&|and) white|\bbswh?\b|baylor (regional|medical center|university "
     r"medical|all saints|surgicare|surgical|emergency|heart)|heart hospital baylor|mclane children", None),
    ("Texas Health Resources", r"\btexas health\b(?! (system|and human|science|tech|east))|harris methodist|\bthr\b|"
     r"huguley|presbyterian hospital|texas institute for surgery", None),
    ("AdventHealth", r"adventhealth|advent health", None),
    ("Houston Methodist", r"houston methodist", None),
    ("Methodist Health System", r"methodist (dallas|richardson|mansfield|charlton|southwest|celina|midlothian|mckinney|"
     r"southlake|hospital for surgery)|\bmrmc\b|\bmlmc\b", None),
    ("HCA Healthcare", r"\bhca\b|medical city|st\.? david'?s|corpus christi medical center|del sol|las palmas|rio grande "
     r"regional|valley regional|conroe regional|heart hospital of austin|wom[ae]n'?s hospital of texas|texas orthopedic "
     r"hospital|west houston medical|mainland|tops surgical|kingwood medical|north cypress|methodist", SA_AREA),
    ("HCA Healthcare", r"\bhca\b|medical city|st\.? david'?s|corpus christi medical center|del sol medical|las palmas|"
     r"rio grande regional|valley regional|heart hospital of austin|texas orthopedic hospital|tops surgical|"
     r"wom[ae]n'?s hospital of texas", None),
    ("Memorial Hermann Health System", r"memorial hermann|\bmhhs\b", None),
    ("CHRISTUS Health", r"christus|mother frances|spohn|good shepherd|santa rosa|jasper memorial|"
     r"st\.? elizabeth|\bctmf\b|children'?s hospital of san antonio", None),
    ("CHRISTUS Health", r"st\.? michael", {"texarkana", "atlanta"}),   # not St. Michael's in Sugar Land
    ("Ascension Seton", r"ascension|\bseton\b|dell seton|dell children", None),
    ("Tenet Healthcare", r"hospitals of providence|valley baptist|resolute health|westover hills baptist|"
     r"baptist (medical center|neighborhood|emergency)|(north central|northeast|mission trail|st\.? luke'?s) baptist", None),
    ("Tenet Healthcare", r"sierra medical center", {"el paso"}),   # The Hospitals of Providence Sierra Campus
    ("Prime Healthcare", r"knapp medical|harlingen medical center", None),
    ("Baptist Hospitals of Southeast Texas", r"baptist (beaumont|hospitals of southeast)", None),
    ("Texas Children's Hospital", r"texas children'?s|texas childrens|\btch\b", None),
    ("Children's Health", r"children'?s health|childrens? medical (center|ctr) (of )?(dallas|plano)|"
     r"children'?s medical (center|ctr) (of )?(dallas|plano)|moody children", None),
    ("Cook Children's", r"cook children", None),
    ("UT Southwestern Medical Center", r"ut ?southwestern|\butsw\b|clements university|zale lipshy", None),
    ("UT MD Anderson Cancer Center", r"anderson cancer|md anderson|m d anderson|\bmdacc\b|\butmda\b", None),
    ("UTMB Health", r"\butmb\b|university of texas medical branch", None),
    ("UT Health San Antonio", r"ut health san antonio|university of texas health science center at san antonio", None),
    ("UTHealth Houston", r"uthealth houston|ut health houston", None),
    ("UT Health East Texas", r"ut health east texas|university of texas health science center at tyler", None),
    ("University Health (Bexar County)", r"university health|university hospital|bexar county hospital", SA_AREA),
    ("Harris Health", r"harris health|lyndon b|\blbj\b|ben taub|harris county hospital", None),
    ("Parkland Health", r"parkland", None),
    ("JPS Health Network", r"\bjps\b|john peter smith|tarrant county hospital", None),
    ("Covenant Health", r"covenant", None),
    ("UMC Health System (Lubbock)", r"university medical center|\bumc\b|lubbock county hospital", {"lubbock"}),
    ("University Medical Center of El Paso", r"university medical center|\bumc\b", {"el paso"}),
    ("Hendrick Health", r"hendrick", None),
    ("Driscoll Health System", r"driscoll", None),
    ("DHR Health", r"\bdhr\b|doctors hospital at renaissance", None),
    ("South Texas Health System", r"south texas health system", None),
    ("Shannon Health", r"\bshannon\b", None),
    ("Midland Health", r"midland memorial|midland health", None),
    ("Medical Center Health System (Odessa)", r"medical center hospital", {"odessa"}),
    ("Legent Health", r"\blegent\b", None),
    ("USPI (United Surgical Partners)", r"surgicare|\buspi\b|united surgical partners", None),
    ("SCA Health", r"\bsca\b|surgical care affiliates", None),
]


def health_systems(text, city, site_type):
    """Health systems a facility belongs to (a few belong to two, e.g. a USPI surgery center co-owned by Baylor)."""
    out = []
    for name, pattern, towns in SYSTEM_RULES:
        if (towns is None or city.lower() in towns) and re.search(pattern, text, re.I) and name not in out:
            out.append(name)
    if "Houston Methodist" in out:   # its names can also contain words of other systems' rules
        out = [s for s in out if s != "Methodist Health System" and not (s == "HCA Healthcare" and city.lower() in HOUSTON_AREA)]
    if site_type == "VA Hospital":
        out.append("Veterans Health Administration")
    if site_type == "Military Hospital":
        out.append("Military Health System")
    return out


def site_name(p):
    """Name for a new-facility site: the filing's facility name, unless that's just an address or a building."""
    fac, name = p["facility_name"], p["name"]
    if p.get("news_name"):
        return p["news_name"]
    if fac and not re.match(r"^\d|n/?a$", fac, re.I) and (STRONG_ASC.search(fac) or STRONG_HOSPITAL.search(fac)):
        return fac
    if STRONG_ASC.search(name) or STRONG_HOSPITAL.search(name):
        return name
    return fac if fac and not re.match(r"^\d|n/?a$", fac, re.I) else name


def load_news():
    path = ROOT / "data/research/news_projects.csv"
    return list(csv.DictReader(open(path, encoding="utf-8"))) if path.exists() else []


def drop_duplicates(projects, review):
    """A project registered twice (same name, address and about the same cost) counts once: the later filing."""
    key = lambda p: (re.sub(r"[^a-z0-9]+", " ", p["name"].lower()).strip(), street_parts(p["street"])[0], p["city"].lower())
    seen, out = {}, []
    for p in sorted(projects, key=lambda p: p["num"], reverse=True):
        k = key(p)
        other = seen.get(k)
        if other and k[1] and abs(p["cost"] - other["cost"]) <= 0.1 * max(p["cost"], other["cost"]):
            review.append((p["num"], p["name"], f"same project as the later filing {other['num']}"))
            continue
        seen.setdefault(k, p)
        out.append(p)
    return sorted(out, key=lambda p: projects.index(p))


def keep_groups_together(projects):
    """Filings that one news report covers belong to one place: the facility of the largest filing that links to
    one, or else one new-facility site (some filings give the architect's address instead of the site's)."""
    groups = defaultdict(list)
    for p in projects:
        if p.get("group"):
            groups[p["group"]].append(p)
    for ps in groups.values():
        lead = max(ps, key=lambda p: (bool(p.get("facility")), p["cost"]))
        for p in ps:
            if lead.get("facility"):
                p["facility"], p["why"] = lead["facility"], "same project as " + lead["num"]
                p["kind"] = "ren" if p["work_code"] in (9002, 9004) else "exp"
            else:
                p["kind"], p["new_type"] = "new", lead["new_type"]
                for k in ("ll", "approx", "how", "street", "city", "zip"):
                    p[k] = lead[k]


def attach_news(projects, rows, facilities, review):
    """Researched news reports: add sources to matching filings, or add announced projects with no filing yet."""
    by_num = {p["num"]: p for p in projects}
    fac_ids = {f["Facility ID"] for f in facilities}
    zips = json.load(open(ROOT / "data/geocode/zip_centers.json"))
    pos = geocode.lookup([(r["address"], r["city"], r["zip"], r["name"]) for r in rows if r["address"]])
    for r in rows:
        sources = [s.split("|", 1) for s in r["sources"].split(" ; ") if "|" in s]
        nums = r["tabs"].split()
        matched = [by_num[n] for n in nums if n in by_num]
        built = set((r.get("builder_tabs") or "").split() or nums[:1])   # the filings the builder source covers
        for p in matched:
            p["news"] += [[t.strip(), u.strip()] for t, u in sources]
            if p["num"] in built:
                p["builder"] = p["builder"] or r["builder"]
            p["opens"] = p["opens"] or r["opens"]
            if r["facility_name"]:
                p["facility_name"] = r["facility_name"]
            p["news_name"] = r["facility_name"] or r["name"]   # names the site if this is a new facility
        if matched or r["stage"] == "skip":
            continue
        g = pos.get(geocode.key(r["address"], r["city"], r["zip"]), {}) if r["address"] else {}
        if r["facility_id"] in fac_ids:
            ll, how = None, ""   # shown at the facility
        elif r["lat"]:   # placed from the report: exact for a street address, approximate for "X Rd & Y Rd" or an area
            ll, how = (float(r["lat"]), float(r["lng"])), "news" if re.match(r"\s*\d+ ", r["address"]) else "news-area"
        elif "lat" in g:
            ll, how = (g["lat"], g["lon"]), g["how"]
        elif r["zip"] in zips:
            ll, how = tuple(zips[r["zip"]]), "zip"
        else:
            review.append(("news", r["name"], "no position for news project"))
            continue
        p = {"num": "", "name": r["name"], "facility_name": r["facility_name"] or r["name"], "scope": r["summary"],
             "cost": money(r["cost"]), "start": r["start"], "end": r["end"], "reg": "", "status": "", "work": "",
             "work_code": 0, "sqft": 0, "owner": r["owner"], "tenant": "", "designer": r["designer"], "addr": "",
             "street": r["address"], "city": r["city"], "zip": r["zip"], "ll": ll, "approx": how in APPROX, "how": how,
             "news": [[t.strip(), u.strip()] for t, u in sources], "builder": r["builder"], "opens": r["opens"],
             "stage": r["stage"], "kind": r["kind"], "news_name": r["facility_name"] or r["name"]}
        if r["facility_id"] in fac_ids:
            p["facility"], p["why"] = r["facility_id"], "news report"
        elif r["kind"] == "new":
            p["new_type"] = r["type"]
        else:
            review.append(("news", r["name"], f"facility {r['facility_id']} not found"))
            continue
        projects.append(p)


def write(sites, projects, review):
    out = {"sites": sites, "projects": [{k: v for k, v in p.items() if k not in ("ll", "street", "work_code", "news_name")}
                                        for p in projects]}
    (ROOT / "data/sites.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    cols = ["num", "name", "facility_name", "kind", "stage", "cost", "start", "end", "opens", "sqft", "work", "status",
            "reg", "scope", "owner", "tenant", "designer", "builder", "addr", "city", "zip", "facility", "why", "news"]
    with open(ROOT / "data/projects.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        for p in sorted(projects, key=lambda p: -p["cost"]):
            w.writerow({**p, "news": " ; ".join(u for _, u in p["news"])})
    with open(ROOT / "data/review.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["filing", "name", "why left off"])
        w.writerows(review)
    c = Counter((p["kind"], p["stage"]) for p in projects)
    print(f"{len(projects)} projects:", dict(sorted(c.items())))
    print(f"{sum(1 for s in sites if s['k'] == 0 and s['pj'])} facilities with projects, "
          f"{sum(1 for s in sites if s['k'] == 1)} new-facility sites; {len(review)} filings left off (data/review.csv)")
    print(Counter(why for _, _, why in review).most_common())


if __name__ == "__main__":
    main()
