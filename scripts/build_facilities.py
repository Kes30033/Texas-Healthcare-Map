"""Build the list of Texas acute care hospitals and ambulatory surgery centers from CMS records.

  python scripts/build_facilities.py RAW_DIR

RAW_DIR holds the downloads made by scripts/download_cms.py:
  pos_hospitals_tx.json   CMS Provider of Services file (hospitals), Texas rows
  pos_iqies_tx.json       CMS Provider of Services file (iQIES: ASCs and others), Texas rows
  hospital_general_tx.json  CMS Care Compare hospital list, Texas rows (for VA and military hospitals)
  tx_counties.json        Census county names by FIPS code

Also adds the hospital campuses in data/campuses.csv, which CMS lists only under a parent hospital's
number (or not at all), placed from data/osm/hospitals.json (OpenStreetMap).

Writes data/facilities.csv: one row per facility.
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "facilities.csv"

HOSPITAL_TYPES = {"01": "Acute Care Hospital", "11": "Critical Access Hospital", "06": "Children's Hospital"}
CONTROL = {"01": "Church", "02": "Private nonprofit", "03": "Other private", "04": "For-profit", "05": "Federal",
           "06": "State", "07": "Local government", "08": "Hospital district", "09": "Physician-owned", "10": "Tribal"}
SPECIALTY_SWITCHES = [("orthpdc_srgry_sw", "Orthopedics"), ("pain_srgry_sw", "Pain"), ("endscpy_srgry_sw", "Endoscopy"),
                      ("opthmlgy_srgry_sw", "Eye"), ("otlrynglgy_srgry_sw", "ENT"), ("plstc_srgry_sw", "Plastic"),
                      ("ob_gyn_srgry_sw", "OB/GYN"), ("ft_srgry_sw", "Foot"), ("dntl_srgry_sw", "Dental"),
                      ("othr_srgry_sw", "Other")]
FIELDS = ["Facility ID", "Name", "Type", "Street Address", "City", "ZIP", "County", "Phone", "Beds",
          "Operating Rooms", "Ownership", "Surgery Specialties", "Medicare Since", "Source", "Note", "Latitude",
          "Longitude"]


def campuses(rows):
    """Rows for data/campuses.csv, placed at their OpenStreetMap position."""
    osm = list(json.loads((ROOT / "data/osm/hospitals.json").read_text(encoding="utf-8")).values())
    by_id = {r["Facility ID"]: r for r in rows}
    out = []
    for c in csv.DictReader(open(ROOT / "data/campuses.csv", encoding="utf-8")):
        if c["osm_name"].startswith("#"):
            continue
        name, _, pick = c["osm_name"].partition("@")
        hits = [o for o in osm if o["name"] == name and (not pick or pick in f'{o["addr"]} {o["city"]}')]
        if not name:   # not in OpenStreetMap: the row gives its own address and position
            hits = [{"addr": c["address"], "city": c["city"], "zip": c["zip"], "lat": float(c["lat"]),
                     "lng": float(c["lng"])}]
        if len(hits) > 1 and all(abs(h["lat"] - hits[0]["lat"]) + abs(h["lng"] - hits[0]["lng"]) < 0.005 for h in hits):
            hits = sorted(hits, key=lambda h: -len(h["addr"]))[:1]   # the same building mapped twice
        if len(hits) != 1:
            sys.exit(f"campuses.csv: {c['osm_name']!r} matches {len(hits)} OpenStreetMap hospitals")
        o, parent = hits[0], by_id.get(c["parent_id"])
        slug = re.sub(r"[^a-z0-9]+", "-", c["name"].lower()).strip("-")
        out.append({
            "Facility ID": f"campus:{slug}", "Name": c["name"], "Type": c["type"], "Street Address": o["addr"],
            "City": o["city"] or c["city"], "ZIP": o["zip"], "County": parent["County"] if parent else "",
            "Phone": "", "Beds": o.get("beds", ""), "Operating Rooms": "",
            "Ownership": parent["Ownership"] if parent else "", "Surgery Specialties": "", "Medicare Since": "",
            "Source": "OpenStreetMap; not listed separately by CMS",
            "Note": c["note"] + (f" (CMS number {c['parent_id']})" if parent else ""),
            "Latitude": o["lat"], "Longitude": o["lng"],
        })
    return out


def clean(v):
    v = (v or "").strip()
    return "" if v in ("Not Available", "Not Applicable") else v


def phone(p):
    p = "".join(ch for ch in clean(p) if ch.isdigit())
    return f"({p[:3]}) {p[3:6]}-{p[6:]}" if len(p) == 10 else ""


def ymd(d):
    d = clean(d).replace("-", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else ""


def title(s):
    """CMS names are upper case; make them readable but keep short words and initials as written."""
    s = clean(s)
    if not s.isupper():
        return s
    keep = {"ASC", "LLC", "LP", "LLP", "PLLC", "PA", "UT", "UTMB", "UMC", "JPS", "HCA", "CHI", "BSW", "MD", "TX", "ER",
            "II", "III", "ENT", "GI", "USMD", "UTHEALTH", "OCH", "DHR", "CHRISTUS", "ICU", "VA", "PC", "SW", "NW", "NE",
            "SE", "US", "HEB", "BSA", "UMMC", "THR", "TOPS", "PRHC", "SETX", "OSH"}
    small = {"of", "and", "the", "at", "for", "in", "on", "de", "del", "la"}
    out = []
    for i, w in enumerate(s.split()):
        core = w.strip(",.()-&")
        if core in keep:
            out.append(w)
        elif i and core.lower() in small:
            out.append(w.lower())
        else:
            out.append("-".join(p[:1].upper() + p[1:].lower() for p in w.split("-")))
    t = " ".join(out)
    return t.replace("'S ", "'s ").replace("’S ", "’s ")


def main():
    raw = Path(sys.argv[1])
    counties = json.load(open(raw / "tx_counties.json"))   # county FIPS -> name
    rows = []

    for r in json.load(open(raw / "pos_hospitals_tx.json", encoding="utf-8")):
        kind = HOSPITAL_TYPES.get(r["PRVDR_CTGRY_SBTYP_CD"])
        if r["PRVDR_CTGRY_CD"] != "01" or r["PGM_TRMNTN_CD"] != "00" or not kind:
            continue
        rows.append({
            "Facility ID": r["PRVDR_NUM"], "Name": title(r["FAC_NAME"]), "Type": kind,
            "Street Address": title(r["ST_ADR"]), "City": title(r["CITY_NAME"]), "ZIP": r["ZIP_CD"][:5],
            "County": counties.get(r["FIPS_CNTY_CD"], ""), "Phone": phone(r["PHNE_NUM"]),
            "Beds": clean(r["BED_CNT"]), "Operating Rooms": clean(r["OPRTG_ROOM_CNT"]),
            "Ownership": CONTROL.get(r["GNRL_CNTL_TYPE_CD"], ""), "Surgery Specialties": "",
            "Medicare Since": ymd(r["ORGNL_PRTCPTN_DT"]), "Source": "CMS Provider of Services (hospitals)",
        })

    # VA and military hospitals aren't in the Provider of Services file; Care Compare lists them
    for r in json.load(open(raw / "hospital_general_tx.json", encoding="utf-8"))["results"]:
        if r["hospital_type"] not in ("Acute Care - Veterans Administration", "Acute Care - Department of Defense"):
            continue
        rows.append({
            "Facility ID": r["facility_id"], "Name": title(r["facility_name"]),
            "Type": "VA Hospital" if "Veterans" in r["hospital_type"] else "Military Hospital",
            "Street Address": title(r["address"]), "City": title(r["citytown"]), "ZIP": r["zip_code"][:5],
            "County": title(r["countyparish"]), "Phone": r["telephone_number"], "Beds": "", "Operating Rooms": "",
            "Ownership": "Government (federal)", "Surgery Specialties": "", "Medicare Since": "",
            "Source": "CMS Care Compare hospital list",
        })

    for r in json.load(open(raw / "pos_iqies_tx.json", encoding="utf-8")):
        if r["prvdr_type_id"] != "11" or r["fed_crtfctn_stus_name"] != "Certified":
            continue
        specs = [label for col, label in SPECIALTY_SWITCHES if r.get(col) == "Yes"]
        rows.append({
            "Facility ID": r["prvdr_num"], "Name": title(r["fac_name"]), "Type": "Ambulatory Surgery Center",
            "Street Address": title(r["st_adr"]), "City": title(r["city_name"]), "ZIP": r["zip_cd"][:5],
            "County": counties.get(r["fips_cnty_cd"], ""), "Phone": phone(r["phne_num"]), "Beds": "",
            "Operating Rooms": clean(r["oprtg_room_cnt"]), "Ownership": clean(r["control_type"]),
            "Surgery Specialties": "; ".join(specs),
            "Medicare Since": clean(r["asc_bgn_srvc_dt"]) or clean(r["orgnl_prtcptn_dt"]),
            "Source": "CMS Provider of Services (iQIES)",
        })

    rows += campuses(rows)
    rows.sort(key=lambda r: (r["Type"] == "Ambulatory Surgery Center", r["City"], r["Name"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(Counter(r["Type"] for r in rows), "->", OUT)


if __name__ == "__main__":
    main()
