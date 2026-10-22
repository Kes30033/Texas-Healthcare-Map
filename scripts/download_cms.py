"""Download the Texas rows of the CMS facility files this map is built from.

  python scripts/download_cms.py [RAW_DIR]     (default: data/raw)

Finds the newest quarterly Provider of Services files in the data.cms.gov catalog, so it keeps
working as CMS posts new quarters. Takes about a minute.
"""
import datetime
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://data.cms.gov/data-api/v1/dataset/{}/data"
CATALOG = "https://data.cms.gov/data.json"
CARE_COMPARE = "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"
COUNTIES = "https://www2.census.gov/geo/docs/reference/codes2020/cou/st48_tx_cou2020.txt"


def get(url, params=None, tries=4):
    if params:
        url += "?" + urllib.parse.urlencode(params, safe=":*")
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curl/8.0"}), timeout=300) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:   # data.cms.gov sometimes answers 403/503 for a minute
            if t == tries - 1:
                raise
            print(f"  {e.code} from {url[:60]}..., retrying")
            time.sleep(20 * (t + 1))


def newest(catalog, title):
    """(quarter start date, API dataset id) of the newest quarter of a Provider of Services file."""
    best = None
    for ds in catalog["dataset"]:   # one catalog entry per quarter, titled "<title> : <quarter end>"
        if ds["title"].split(" : ")[0] != title:
            continue
        api = [d for d in ds.get("distribution", []) if d.get("format") == "API" and d.get("temporal")]
        if api:
            start = api[0]["temporal"][0]["startDate"]
            if not best or start > best[0]:
                best = (start, api[0]["accessURL"].split("/dataset/")[1].split("/")[0])
    if not best:
        sys.exit(f"Couldn't find {title!r} in the CMS catalog")
    print(f"{title}: quarter starting {best[0]}")
    return best


def all_rows(dataset, filters):
    rows, offset = [], 0
    while True:
        page = get(API.format(dataset), {"size": 5000, "offset": offset, **{f"filter[{k}]": v for k, v in filters.items()}})
        rows += page
        if len(page) < 5000:
            return rows
        offset += 5000


def main():
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    catalog = get(CATALOG)

    quarter, dataset = newest(catalog, "Provider of Services File - Quality Improvement and Evaluation System")
    hosp = all_rows(dataset, {"STATE_CD": "TX", "PRVDR_CTGRY_CD": "01"})
    hosp = [r for r in hosp if r["PGM_TRMNTN_CD"] == "00"]
    iq = all_rows(newest(catalog, "Provider of Services File - Internet Quality Improvement and Evaluation System")[1],
                  {"state_cd": "TX", "prvdr_type_id": "11"})
    hgi = get(CARE_COMPARE, {"conditions[0][property]": "state", "conditions[0][value]": "TX",
                             "conditions[0][operator]": "=", "limit": 1500})
    with urllib.request.urlopen(COUNTIES, timeout=60) as r:   # STATE|STATEFP|COUNTYFP|COUNTYNS|COUNTYNAME|...
        counties = {line.split("|")[2]: line.split("|")[4].removesuffix(" County")
                    for line in r.read().decode().splitlines()[1:] if line}

    for name, data in [("pos_hospitals_tx.json", hosp), ("pos_iqies_tx.json", iq),
                       ("hospital_general_tx.json", hgi), ("tx_counties.json", counties)]:
        (raw / name).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    (raw / "DOWNLOADED_ON").write_text(datetime.date.today().isoformat() + "\n", encoding="utf-8")
    (raw / "CMS_QUARTER.json").write_text(json.dumps({"start": quarter}), encoding="utf-8")
    print(f"{len(hosp)} active hospital records, {len(iq)} ASC records, {len(hgi['results'])} Care Compare hospitals -> {raw}")


if __name__ == "__main__":
    main()
