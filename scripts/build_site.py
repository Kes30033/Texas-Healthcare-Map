"""Build the website and the spreadsheet from data/sites.json (made by scripts/build_projects.py).

  python scripts/build_site.py                      -> docs/  (GitHub Pages: street + satellite maps)
  python scripts/build_site.py --artifact <dir>     -> <dir>  (Claude artifact: hand-drawn map only,
                                                              because outside map images are blocked there)
Also writes data/Texas_Hospital_Construction.xlsx.
"""
import argparse
import datetime
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import xlsxwriter

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
TYPES = [("Acute Care Hospital", "hosp"), ("Critical Access Hospital", "hosp"), ("Children's Hospital", "hosp"),
         ("VA Hospital", "hosp"), ("Military Hospital", "hosp"), ("Ambulatory Surgery Center", "asc"),
         ("New hospital", "hosp"), ("New surgery center", "asc")]
STAGE = {"uc": "Under construction", "filed": "Filed, not started", "ann": "Announced"}
KIND = {"new": "New hospital or surgery center", "exp": "Expansion / addition", "ren": "Renovation"}
SITE_KEYS = ["k", "id", "n", "lat", "lng", "approx", "addr", "city", "zip", "county", "phone", "beds", "ors", "own",
             "spec", "since", "note", "pj"]
PROJECT_KEYS = ["num", "name", "kind", "stage", "cost", "start", "end", "opens", "sqft", "work", "tenant", "reg", "status",
                "scope", "addr", "news"]
FIRM_FILLER = set("""inc llc lp llp pllc pc corp corporation co company ltd limited the incorporated dba architects
architect architecture architectural group design designs studio and""".split())


def firm_key(name):
    """'HKS, Inc.', 'HKS Architects' and 'hks inc' -> 'hks', so one firm is one search entry."""
    s = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower().replace("&", " and ").replace("+", " and "))
    key = "".join(w for w in s.split() if w not in FIRM_FILLER)
    key = re.sub(r"(inc|llc|pllc|ltd|corp)$", "", key) or key   # "HKSinc"
    return "" if key in ("na", "n", "tbd", "none", "self", "owner", "unknown") else key


class Names:
    """Spelling variants of the same firm or owner, merged; each is shown by its most common spelling."""
    def __init__(self):
        self.keys, self.spellings = {}, []

    def add(self, name):
        name = re.sub(r"\s+", " ", (name or "").strip(" ,"))
        key = firm_key(name)
        if not key:
            return None
        if key not in self.keys:
            self.keys[key] = len(self.spellings)
            self.spellings.append(Counter())
        i = self.keys[key]
        self.spellings[i][name.title() if name.isupper() and len(name) > 4 else name] += 1
        return i

    def names(self):
        return [c.most_common(1)[0][0] for c in self.spellings]


def pack(data):
    type_idx = {t: i for i, (t, _) in enumerate(TYPES)}
    systems = sorted({x for s in data["sites"] for x in s["sys"]})
    sys_idx = {x: i for i, x in enumerate(systems)}
    sites = []
    for s in data["sites"]:
        o = {k: s[k] for k in SITE_KEYS if s.get(k) not in (None, "", False, [])}
        o["k"], o["pj"], o["t"] = s["k"], s["pj"], type_idx[s["type"]]
        o["lat"], o["lng"] = round(s["lat"], 5), round(s["lng"], 5)
        if s["sys"]:
            o["sys"] = [sys_idx[x] for x in s["sys"]]
        sites.append(o)
    firms, builders, owners = Names(), Names(), Names()
    projects = []
    for p in data["projects"]:
        o = {k: p[k] for k in PROJECT_KEYS if p.get(k) not in (None, "", 0, [])}
        d, ow = firms.add(p["designer"]), owners.add(p["owner"])
        b = [i for i in (builders.add(x) for x in (p.get("builder") or "").split(";")) if i is not None]
        if d is not None:
            o["d"] = d
        if ow is not None:
            o["o"] = ow
        if b:
            o["b"] = b
        projects.append(o)
    return {"types": [{"label": t, "group": g} for t, g in TYPES], "sites": sites, "projects": projects,
            "systems": systems, "firms": firms.names(), "builders": builders.names(), "owners": owners.names()}


def spreadsheet(data, path, updated, cms_date):
    wb = xlsxwriter.Workbook(path)
    head = wb.add_format({"bold": True, "bg_color": "#13191C", "font_color": "#FFFFFF", "text_wrap": True, "valign": "top"})
    money = wb.add_format({"num_format": "$#,##0"})
    wrap = wb.add_format({"text_wrap": True, "valign": "top"})
    link = wb.add_format({"font_color": "#2A78D6", "underline": 1})
    bold = wb.add_format({"bold": True})

    sites = data["sites"]
    site_of = {j: s for s in sites for j in s["pj"]}

    ws = wb.add_worksheet("Projects")
    cols = [("Facility", 34), ("Facility type", 22), ("City", 14), ("County", 12), ("Project", 40), ("Stage", 18),
            ("Kind", 22), ("Estimated cost", 15), ("Est. start", 11), ("Est. finish", 11), ("Opens (news)", 12),
            ("Sq ft", 10), ("Owner", 28), ("Architect / design firm", 28), ("Builder (news)", 20),
            ("Scope of work", 60), ("Project address", 34), ("State filing", 16), ("Filed", 11), ("Filing status", 18),
            ("News sources", 50), ("Health system", 30)]
    for c, (h, w) in enumerate(cols):
        ws.write(0, c, h, head)
        ws.set_column(c, c, w)
    order = sorted(range(len(data["projects"])), key=lambda j: (list(STAGE).index(data["projects"][j]["stage"]),
                                                                 -data["projects"][j]["cost"]))
    for r, j in enumerate(order, 1):
        p, s = data["projects"][j], site_of[j]
        row = [s["n"], s["type"], s["city"], s.get("county", ""), p["name"], STAGE[p["stage"]], KIND[p["kind"]],
               p["cost"] or None, p["start"], p["end"], p.get("opens", ""), p["sqft"] or None, p["owner"], p["designer"],
               p.get("builder", ""), p["scope"], p["addr"] or ", ".join(x for x in (p.get("city"),) if x), p["num"],
               p["reg"], p["status"], " ; ".join(u for _, u in p["news"]), "; ".join(s["sys"])]
        for c, v in enumerate(row):
            if c == 7 and v:
                ws.write_number(r, c, v, money)
            elif c == 17 and v:
                ws.write_url(r, c, f"https://www.tdlr.texas.gov/TABS/Search/Project/{v}", link, v)
            elif v is not None:
                ws.write(r, c, v, wrap if c == 15 else None)
    ws.freeze_panes(1, 1)
    ws.autofilter(0, 0, len(order), len(cols) - 1)

    ws = wb.add_worksheet("Facilities")
    cols = [("Name", 40), ("Type", 24), ("Street address", 30), ("City", 14), ("ZIP", 7), ("County", 12),
            ("Phone", 15), ("Beds", 6), ("Operating rooms", 9), ("Ownership", 18), ("Surgery types", 30),
            ("CMS number", 11), ("Active projects", 9), ("Under construction", 11), ("Filed, not started", 11),
            ("Announced", 10), ("Total est. cost", 15), ("Largest project", 50), ("Map position", 14), ("Note", 40),
            ("Health system", 30)]
    for c, (h, w) in enumerate(cols):
        ws.write(0, c, h, head)
        ws.set_column(c, c, w)
    rows = sorted(sites, key=lambda s: (-sum(data["projects"][j]["cost"] for j in s["pj"]), s["n"]))
    for r, s in enumerate(rows, 1):
        ps = [data["projects"][j] for j in s["pj"]]
        big = max(ps, key=lambda p: p["cost"])["name"] if ps else ""
        row = [s["n"], s["type"], s.get("addr", ""), s["city"], s.get("zip", ""), s.get("county", ""), s.get("phone", ""),
               s.get("beds", ""), s.get("ors", ""), s.get("own", ""), s.get("spec", ""), s.get("id", ""), len(ps),
               sum(p["stage"] == "uc" for p in ps), sum(p["stage"] == "filed" for p in ps),
               sum(p["stage"] == "ann" for p in ps), sum(p["cost"] for p in ps) or None, big,
               "ZIP/city center" if s.get("approx") else "Street address", s.get("note", ""), "; ".join(s["sys"])]
        for c, v in enumerate(row):
            if c == 16 and v:
                ws.write_number(r, c, v, money)
            elif c in (7, 8) and str(v).isdigit():
                ws.write_number(r, c, int(v))
            elif v is not None:
                ws.write(r, c, v)
    ws.freeze_panes(1, 1)
    ws.autofilter(0, 0, len(rows), len(cols) - 1)

    ws = wb.add_worksheet("About")
    ws.set_column(0, 0, 120)
    lines = [
        ("Texas hospitals, surgery centers and their construction projects", bold),
        (f"Projects searched {updated}. Facility lists from CMS, quarter starting {cms_date}.", None), ("", None),
        ("Facilities: CMS Provider of Services files (every Medicare-certified short-term acute care, critical access and "
         "children's hospital, and every certified ambulatory surgery center, active in the latest quarter), plus VA and "
         "military hospitals from CMS Care Compare. Facilities licensed by Texas but not Medicare-certified are not included.", wrap),
        ("Projects: Texas Department of Licensing and Regulation (TDLR) Texas Architectural Barriers System (TABS). Every "
         "building project in Texas costing $50,000 or more must be registered there, with owner, design firm, address, "
         "cost, type of work and estimated start and completion dates. Filings since 2021 that are not closed or inspected, "
         "and whose estimated completion is no more than 150 days past, are included.", wrap),
        ("Stage: 'Filed, not started' = the filing's estimated start date is still ahead (permits filed, design firm under "
         "contract). 'Under construction' = the estimated start date has passed and the work isn't finished. 'Announced' = "
         "reported in the news with no state filing found yet. Filing dates are estimates, so projects can run late.", wrap),
        ("Kind: 'New' = a hospital or surgery center that isn't open yet (new building or a build-out). 'Expansion' = new "
         "construction or an addition at an existing facility. 'Renovation' = work inside an existing facility.", wrap),
        ("Federal projects (VA, military) don't file with TDLR, so they appear only when found in the news.", wrap),
    ]
    for r, (t, f) in enumerate(lines):
        ws.write(r, 0, t, f)
    wb.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", metavar="DIR", help="build the Claude artifact version into DIR")
    args = ap.parse_args()
    data = json.loads((ROOT / "data/sites.json").read_text(encoding="utf-8"))
    updated = (ROOT / "data/tabs/SEARCHED_ON").read_text(encoding="utf-8").strip()
    cms = json.loads((ROOT / "data/raw/CMS_QUARTER.json").read_text(encoding="utf-8"))["start"]

    if args.artifact:
        out = Path(args.artifact).resolve()
        if out == ROOT or ROOT in out.parents:
            sys.exit("Choose a folder outside the project for --artifact")
    else:
        out = ROOT / "docs"
    (out / "data").mkdir(parents=True, exist_ok=True)
    m = pack(data)
    m["updated"], m["cmsDate"] = updated, cms
    (out / "data/map.json").write_text(json.dumps(m, separators=(",", ":")), encoding="utf-8")
    shutil.copy(ROOT / "data/basemap/basemap.json", out / "data/basemap.json")

    d, c = datetime.date.fromisoformat(updated), datetime.date.fromisoformat(cms)
    page = (SITE / "index.template.html").read_text(encoding="utf-8")
    page = page.replace("<!--UPDATED-->", f"{d:%b} {d.day}, {d.year}").replace("<!--CMS_DATE-->", f"the {c:%B %Y} quarter")
    if args.artifact:
        css = (SITE / "vendor/leaflet-1.9.4.css").read_text(encoding="utf-8")
        page = page.replace("<!--LEAFLET_CSS-->", f"<style>\n{css}\n</style>").replace("/*TILES*/true", "false")
    else:
        page = ('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                '<meta name="description" content="Map of every acute care hospital and ambulatory surgery center in Texas, '
                'with renovations, expansions, construction underway and new facilities filed with the state.">\n'
                + page.replace("<!--LEAFLET_CSS-->", '<link rel="stylesheet" '
                               'href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">'))
        (out / ".nojekyll").write_text("")
    (out / "index.html").write_text(page, encoding="utf-8")
    spreadsheet(data, ROOT / "data/Texas_Hospital_Construction.xlsx", updated, cms)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"wrote {out} ({size / 1e6:.1f} MB) and data/Texas_Hospital_Construction.xlsx")


if __name__ == "__main__":
    main()
