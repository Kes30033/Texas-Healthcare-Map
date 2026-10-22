"""Find construction projects at Texas hospitals and surgery centers in TDLR's TABS registry.

Every building project in Texas costing $50,000 or more must be registered with the Texas Department
of Licensing and Regulation (Texas Architectural Barriers Act) before construction, with the owner,
design firm, address, estimated cost, type of work and estimated start and completion dates.

  python scripts/tabs_harvest.py keywords FIELD     search one field (FacilityName, ProjectName, OwnerName)
  python scripts/tabs_harvest.py addresses [K N]    search the street address of every facility in data/facilities.csv
                                                    (K N: only every Nth facility from the Kth, for parallel runs)

Results go to data/tabs/search/<name>.jsonl, one project per line. Each search remembers which
queries it has finished (<name>.done), so an interrupted run picks up where it stopped.
"""
import csv
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tabs" / "search"
SEARCH = "https://www.tdlr.texas.gov/TABS/Search/SearchProjects"
FORM = "https://www.tdlr.texas.gov/TABS/Search"
UA = "Mozilla/5.0 (compatible; Texas-Healthcare-Map; github.com/Kes30033/Texas-Healthcare-Map)"
SINCE = "2021-01-01"   # projects registered earlier are finished or stalled
COLS = ["ProjectId", "ProjectNumber", "ProjectName", "ProjectCreatedOn", "ProjectStatus", "FacilityName",
        "City", "County", "TypeOfWork", "EstimatedCost", "DataVersionId"]

GENERIC = ["hospital", "medical center", "med ctr", "medical ctr", "surgery", "surgical", "surgi", "ASC",
           "health", "emergency", "patient tower", "bed tower", "patient care tower", "ICU", "NICU", "cath lab",
           "operating room", "endoscopy", "infirmary", "medical campus"]
SYSTEMS = ["Baylor", "Scott & White", "BSW", "Methodist", "Memorial Hermann", "HCA", "Medical City", "Texas Health",
           "CHRISTUS", "St. David", "St David", "Seton", "Ascension", "Dell Children", "Cook Children",
           "Texas Children", "Covenant", "UMC", "University Health", "Parkland", "JPS", "UT Health", "UTHealth",
           "UTMB", "UT Southwestern", "UTSW", "MD Anderson", "Harris Health", "Hendrick", "Baptist", "St. Luke",
           "St Luke", "Hospitals of Providence", "Providence", "Del Sol", "Las Palmas", "Shannon", "Midland Memorial",
           "Medical Center Health", "Driscoll", "Valley Baptist", "DHR", "Doctors Hospital", "Knapp",
           "Mission Regional", "Northwest Texas", "BSA", "Hillcrest", "Texas Tech", "Titus", "Wadley", "Paris Regional",
           "Longview Regional", "UT Tyler", "Mother Frances", "Good Shepherd", "Huguley", "Wise Health", "Lakeway",
           "Heart Hospital", "Legent", "USPI", "Surgery Partners", "Texas Orthopedic", "Spohn", "Corpus Christi Medical",
           "Citizens Medical", "DeTar", "Memorial Medical", "Brazosport", "Kingwood", "Woodlands", "Conroe Regional",
           "Ben Taub", "LBJ", "Lyndon B. Johnson", "Veterans", "VA Medical", "Brooke Army", "Darnall", "Emerus",
           "Kelsey", "Houston Physicians", "Nix", "Steward", "Lifepoint", "Prime Healthcare", "Universal Health",
           "Community Health Systems", "Tenet", "Texas Oncology", "Children's Health", "Childrens Health",
           "Texas Spine", "Orthopedic Hospital", "Surgical Hospital", "Specialty Hospital", "Regional Medical",
           "Memorial Hospital", "County Hospital", "General Hospital", "Hospital District"]
FIELDS = {"FacilityName": GENERIC + SYSTEMS, "ProjectName": GENERIC + SYSTEMS, "OwnerName": GENERIC[:9] + SYSTEMS}


def post(params, start, tries=5):
    body = {"draw": "1", "start": str(start), "length": "100", "order[0][column]": "3", "order[0][dir]": "desc"}
    body.update({f"columns[{i}][data]": c for i, c in enumerate(COLS)})
    body.update(params)
    data = urllib.parse.urlencode(body).encode()
    for t in range(tries):
        try:
            req = urllib.request.Request(SEARCH, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:   # the registry is sometimes slow; back off and try again
            print("  retry", t + 1, e, file=sys.stderr, flush=True)
            time.sleep(5 * (t + 1))
    raise RuntimeError(f"TABS search failed for {params}")


def search(params):
    """All projects registered since SINCE that match params (newest first; the registry pages by 100)."""
    rows, start = [], 0
    while True:
        d = post(params, start)
        page = d.get("data", [])
        rows += [r for r in page if r["ProjectCreatedOn"][:10] >= SINCE]
        start += len(page)
        if not page or start >= d.get("recordsFiltered", 0) or page[-1]["ProjectCreatedOn"][:10] < SINCE:
            return rows
        time.sleep(0.5)


def run(name, queries):
    """queries: [(label, params)] -> appends matches to OUT/<name>.jsonl, skipping labels already done."""
    OUT.mkdir(parents=True, exist_ok=True)
    done_file, out_file = OUT / f"{name}.done", OUT / f"{name}.jsonl"
    done = set(done_file.read_text(encoding="utf-8").splitlines()) if done_file.exists() else set()
    for n, (label, params) in enumerate(queries):
        if label in done:
            continue
        rows = search(params)
        with open(out_file, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(dict(r, query=label)) + "\n")
        with open(done_file, "a", encoding="utf-8") as f:
            f.write(label + "\n")
        print(f"[{n + 1}/{len(queries)}] {label!r}: {len(rows)}", flush=True)
        time.sleep(0.5)
    (ROOT / "data" / "tabs" / "SEARCHED_ON").write_text(time.strftime("%Y-%m-%d") + "\n", encoding="utf-8")


def city_ids():
    """TABS city name -> id, from the options of the search form."""
    with urllib.request.urlopen(urllib.request.Request(FORM, headers={"User-Agent": UA}), timeout=90) as r:
        page = r.read().decode("utf-8", "replace")
    block = page[page.index('id="filter-location-city"'):]
    block = block[:block.index("</select>")]
    return {html.unescape(m[1]).upper(): m[0] for m in re.findall(r'<option value="(\d+)">([^<]+)</option>', block)}


def address_queries():
    """One query per facility: its street number and first street word, in its city."""
    ids = city_ids()
    (ROOT / "data" / "tabs").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "tabs" / "cities.json").write_text(json.dumps({v: k for k, v in ids.items()}), encoding="utf-8")
    out = []
    for r in csv.DictReader(open(ROOT / "data" / "facilities.csv", encoding="utf-8")):
        m = re.match(r"\s*(\d+)\s+(?:[NSEW]\.?\s+|North\s+|South\s+|East\s+|West\s+)?([A-Za-z0-9]+)", r["Street Address"])
        city = ids.get(r["City"].upper())
        if not m or not city:
            print("  no address query for", r["Name"], "|", r["Street Address"], r["City"])
            continue
        out.append((f'{r["Facility ID"]}', {"LocationAddress": f"{m[1]} ", "LocationCity": city}))
    return out


def main():
    if sys.argv[1] == "keywords":
        field = sys.argv[2]
        run(field, [(f"{field}:{kw}", {field: kw}) for kw in FIELDS[field]])
    elif sys.argv[1] == "addresses":   # optional "K N": do every Nth facility starting at K, to run in parallel
        k, n = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (0, 1)
        run("addresses", address_queries()[k::n])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
