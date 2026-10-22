"""Suggest TABS filings for the rows of data/research/news_projects.csv that have no "tabs" numbers yet.

  python scripts/suggest_news_matches.py [KEY ...]

For each row, lists the saved filings in the same city whose name, facility or scope contains one of the
row's "match" words (separated by |), largest first. Copy the right numbers into the row's "tabs" column.
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    filings = []
    for f in (ROOT / "data/tabs/details").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        cost = int(re.sub(r"[^\d]", "", d.get("Estimated Cost", "") or "0") or 0)
        filings.append((f.stem, d, cost))
    keys = set(sys.argv[1:])
    for r in csv.DictReader(open(ROOT / "data/research/news_projects.csv", encoding="utf-8")):
        if (keys and r["key"] not in keys) or (not keys and (r["tabs"] or not r["match"])):
            continue
        words = [w.lower() for w in r["match"].split("|") if w]
        hits = []
        for num, d, cost in filings:
            text = " ".join(d.get(k, "") for k in ("Project Name", "Facility Name", "Scope of Work", "Owner Name")).lower()
            if r["city"].lower() in d.get("Location Address", "").lower() and any(w in text for w in words):
                hits.append((cost, num, d))
        print(f"\n== {r['key']}: {r['name']} ({r['city']})")
        for cost, num, d in sorted(hits, reverse=True)[:8]:
            print(f"  {num}  ${cost:>13,}  {d.get('Start Date', '')} -> {d.get('Completion Date', '')}  "
                  f"{d.get('Type of Work', '')[:12]:12}  {d.get('Project Name', '')[:60]} | {d.get('Location Address', '')[:45]}")


if __name__ == "__main__":
    main()
